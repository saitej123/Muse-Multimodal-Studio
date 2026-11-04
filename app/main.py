"""FastAPI application entrypoint.

Serves the shadcn-style frontend and exposes the pipeline API:
  GET  /api/capabilities         -> which optional tools are available
  POST /api/jobs                 -> upload PDF/image, start pipeline (multipart)
  GET  /api/jobs/{id}            -> poll job snapshot
  GET  /api/jobs/{id}/stream     -> live SSE stream of job updates
  PATCH/api/jobs/{id}/content    -> edit step content (extracted_text, narration)
  POST /api/jobs/{id}/review-content -> duplicate-slide + voice-sync review
  GET  /files/{id}/{path}        -> download generated artifacts
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
)
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, runner
from . import automation as auto
from . import ui_theme
from .capabilities import detect_capabilities
from .config import BASE_DIR, WORKSPACE_DIR, get_settings
from .jobs import store
from .logging_setup import log
from .orchestrator import STAGE_FUNCS, run_from_stage, run_pipeline, run_single_stage
from .video_options import (
    normalize_video_options,
    public_style_categories,
    public_video_formats,
    public_video_styles,
    public_video_themes,
    public_visual_presets,
)

app = FastAPI(title="Multimodal Studio", version="2.3.0")

STATIC_DIR = BASE_DIR / "frontend"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

_JOB_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def _automation_output_dir() -> Path:
    """Resolved automation output root (honors ``AUTO_OUTPUT_DIR``)."""
    return get_settings().auto_output_path


def _safe_job_dir(job_id: str) -> Path:
    """Resolve a job workspace, rejecting path traversal."""
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(400, "Invalid job id")
    from .workspace_store import resolve_job_dir

    root = WORKSPACE_DIR.resolve()
    try:
        base = resolve_job_dir(job_id, create=False).resolve()
    except Exception:
        base = (WORKSPACE_DIR / job_id).resolve()
    if not base.is_relative_to(root):
        raise HTTPException(403, "Forbidden")
    if not base.is_dir():
        raise HTTPException(404, "Job not found")
    return base


def _safe_cron_dir(folder: str) -> Path:
    """Resolve an automation output folder, rejecting path traversal."""
    if not folder or folder in (".", "..") or "/" in folder or "\\" in folder:
        raise HTTPException(400, "Invalid folder")
    root = _automation_output_dir().resolve()
    root.mkdir(parents=True, exist_ok=True)
    base = (root / folder).resolve()
    if not base.is_relative_to(root):
        raise HTTPException(403, "Forbidden")
    return base


def _prefer_cron_video(base: Path) -> Path | None:
    """Prefer long-form ``video/video.mp4`` over reel when publishing."""
    candidates = [
        base / "video" / "video.mp4",
        base / "video_video.mp4",
        base / "reel" / "video.mp4",
        base / "reel_video.mp4",
    ]
    for c in candidates:
        if c.is_file():
            return c
    videos = sorted(base.rglob("*.mp4"))
    # Prefer paths containing "/video/" or starting with video_
    videos.sort(
        key=lambda p: (
            0 if "/video/" in p.as_posix() or p.name.startswith("video_") else 1,
            p.as_posix(),
        )
    )
    return videos[0] if videos else None


def _prefer_cron_thumb(base: Path) -> Path | None:
    candidates = [
        base / "video" / "thumbnail.png",
        base / "video_thumbnail.png",
        base / "reel" / "thumbnail.png",
        base / "reel_thumbnail.png",
    ]
    for c in candidates:
        if c.is_file():
            return c
    thumbs = sorted(base.rglob("*thumb*.png"))
    return thumbs[0] if thumbs else None


def _load_cron_publish_meta(base: Path) -> dict:
    for rel in ("video/metadata.json", "video_metadata.json", "reel/metadata.json"):
        path = base / rel
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


@app.on_event("startup")
def _hydrate_sessions() -> None:
    # Load persisted job history from SQLite so sessions survive restarts.
    store.hydrate()
    # Apply admin runtime overrides (LLM provider / models / image backend).
    from . import runtime_settings as runtime_settings_mod

    runtime_settings_mod.load_on_startup()
    # Start the paper -> video automation scheduler (twice/day, off-hours).
    auto.start_scheduler()

# Cache-busting token for static assets: prefer JS/CSS mtimes so a code edit
# invalidates browsers even without a process restart; fall back to start time.
import time as _time

def _asset_version() -> str:
    try:
        stamps = [
            (STATIC_DIR / name).stat().st_mtime_ns
            for name in (
                "app.js", "styles.css", "slide_kit.js",
                "chitti.js", "chitti.css", "muse-mark.js",
                "favicon.svg", "favicon.ico", "favicon-256.png",
            )
            if (STATIC_DIR / name).exists()
        ]
        if stamps:
            return str(max(stamps) // 1_000_000)
    except OSError:
        pass
    return str(int(_time.time()))


ASSET_VERSION = _asset_version()


@app.middleware("http")
async def _cache_headers(request: Request, call_next):
    """Keep HTML/API fresh; let versioned /static/ revalidate quickly."""
    response = await call_next(request)
    path = request.url.path or ""
    if path.startswith("/static/"):
        # Query ``?v=`` already busts; avoid long stale caches after deploys.
        response.headers.setdefault(
            "Cache-Control", "public, max-age=0, must-revalidate"
        )
    elif path == "/" or path.startswith("/api/"):
        response.headers.setdefault(
            "Cache-Control", "no-cache, no-store, must-revalidate"
        )
    return response


ALLOWED_SUFFIXES = {
    # documents
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md", ".markdown",
    ".rtf", ".odt", ".html", ".htm", ".epub", ".csv", ".xlsx", ".xlsm",
    # images
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif",
}
STUDIO_UPLOAD_MAX_BYTES = 80 * 1024 * 1024

# Interview ingest / mock clip caps (bytes read into memory)
IV_INGEST_MAX_BYTES = 40 * 1024 * 1024  # 40 MB
IV_CLIP_MAX_BYTES = 80 * 1024 * 1024  # 80 MB


async def _read_upload_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read upload into memory with a hard size cap."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                413,
                f"File too large (max {max_bytes // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


# ============================================================ single local user ==
# There is no login screen. Every request runs as one local identity, so job
# ownership checks and the admin tabs keep working without a session cookie.

LOCAL_USER = auth.User(
    id="local",
    email="local@studio",
    username="Studio",
    role="admin",
)


def _current_user(request: Request) -> auth.User:
    request.state.user = LOCAL_USER
    return LOCAL_USER


def require_user(request: Request) -> auth.User:
    return _current_user(request)


def require_admin(request: Request) -> auth.User:
    return _current_user(request)


def _job_for_user(request: Request, job_id: str):
    """Return a job. The app has one local user, so any job is reachable."""
    require_user(request)
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.middleware("http")
async def local_user_middleware(request: Request, call_next):
    """Attach the single local identity. There is no login screen to gate on."""
    request.state.user = LOCAL_USER
    return await call_next(request)


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    """Identity for the UI. There is no login, so this is always the local user."""
    return {"user": LOCAL_USER.public(), "local": True}


@app.get("/api/admin/costs")
def admin_costs(request: Request, days: int = 30, debug: bool = False) -> dict:
    """LLM / paid-API cost report for the admin dashboard."""
    require_admin(request)
    from . import costs

    return costs.report(days=max(1, min(days, 365)), debug=bool(debug))


# --------------------------------------------------------------- voice library --

@app.get("/api/voices")
def voices_list(request: Request) -> dict:
    """Studio voices used for narration."""
    require_user(request)
    from .pipeline import tts

    try:
        default_id = tts.default_voice()
    except ValueError:
        default_id = "Kore"
    return {
        "voices": tts.list_voices(),
        "default_voice": default_id,
        "muse_tts": tts.narration_available(),
        "engine": tts.selected_engine(),
        "model": "narration",
    }


# ----------------------------------------------------------- UI color palette --

VOICE_PREVIEW_TEXT = (
    "Hello! This is a quick sample of how this voice will sound in your video. "
    "It's clear, warm, and natural."
)

VOICE_CLONE_RECORDING_TEXT = (
    "The quick brown fox jumps over the lazy dog. Every video deserves a clear, "
    "natural narration that feels warm and human. Please read this paragraph at your "
    "normal speaking pace, in a quiet room, with the microphone about six inches away. "
    "Take a breath, then finish with: this is my voice for Multimodal Studio."
)


@app.get("/api/ui-palette")
def ui_palette_get(request: Request) -> dict:
    """Active app color palette (public so the studio theme applies everywhere)."""
    return {"palette": ui_theme.get_palette()}


@app.get("/api/admin/ui-palette")
def admin_ui_palette_get(request: Request) -> dict:
    require_admin(request)
    return ui_theme.palette_response()


class UiPaletteUpdate(BaseModel):
    name: str = ""
    primary: str = ""
    primary_foreground: str = ""
    brand: str = ""
    brand_2: str = ""
    blue: str = ""
    blue_2: str = ""


@app.put("/api/admin/ui-palette")
def admin_ui_palette_put(req: UiPaletteUpdate, request: Request) -> dict:
    require_admin(request)
    palette = ui_theme.save_palette(req.model_dump())
    log.bind(task="ui").info(f"admin updated UI palette -> {palette.get('name')}")
    return {"ok": True, "palette": palette}


# -------------------------------------------------------- social credentials --

@app.get("/api/admin/social-credentials")
def admin_social_credentials_get(request: Request) -> dict:
    require_admin(request)
    from . import social_credentials as sc
    return sc.public_status()


class SocialCredUpdate(BaseModel):
    platform: str
    enabled: bool | None = None
    auto_post: bool | None = None
    fields: dict[str, str] | None = None


@app.put("/api/admin/social-credentials")
def admin_social_credentials_put(req: SocialCredUpdate, request: Request) -> dict:
    require_admin(request)
    from . import social_credentials as sc
    updates: dict = {}
    if req.enabled is not None:
        updates["enabled"] = req.enabled
    if req.auto_post is not None:
        updates["auto_post"] = req.auto_post
    if req.fields:
        updates.update(req.fields)
    try:
        return sc.update_platform(req.platform, updates)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class SocialCredClear(BaseModel):
    platform: str
    key: str


@app.post("/api/admin/social-credentials/clear")
def admin_social_credentials_clear(req: SocialCredClear, request: Request) -> dict:
    require_admin(request)
    from . import social_credentials as sc
    try:
        return sc.clear_field(req.platform, req.key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/social/status")
def social_status(request: Request) -> dict:
    """Which platforms are ready to post (no secrets)."""
    require_user(request)
    from . import social_credentials as sc
    data = sc.public_status()
    return {
        "platforms": [
            {
                "id": p["id"],
                "label": p["label"],
                "enabled": p["enabled"],
                "auto_post": p["auto_post"],
                "ready": p["ready"],
            }
            for p in data.get("platforms", [])
        ]
    }


class SocialPostRequest(BaseModel):
    platform: str
    # video | image | carousel | auto
    mode: str = "auto"


@app.post("/api/jobs/{job_id}/social-post")
def social_post_endpoint(job_id: str, req: SocialPostRequest, request: Request) -> dict:
    """Post video / image / carousel + caption to a configured platform."""
    job = _job_for_user(request, job_id)
    from .pipeline import social_post as social_post_mod

    try:
        result = social_post_mod.post_to_platform(job, req.platform, mode=req.mode or "auto")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e
    # Persist last results per platform
    prev = dict(job.content.get("social_post_results") or {})
    if isinstance(prev, list):
        prev = {r.get("platform", f"p{i}"): r for i, r in enumerate(prev)}
    prev[req.platform] = result
    store.set_content(job, "social_post_results", prev)
    if req.platform == "youtube" and result.get("result"):
        store.set_artifact(job, "youtube", result["result"])
    return result


@app.post("/api/jobs/{job_id}/social-prepare-carousel")
def social_prepare_carousel(job_id: str, request: Request) -> dict:
    """Resize slide frames to Instagram square images (downloadable)."""
    job = _job_for_user(request, job_id)
    from .pipeline import social_post as social_post_mod

    work, _, _, slides = social_post_mod._work_paths(job)
    if not slides:
        raise HTTPException(400, "No slide images available yet — finish capture first.")
    try:
        staged = social_post_mod.prepare_instagram_carousel(work, slides)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e
    media = [f"/files/{job.id}/social/ig_carousel/{p.name}" for p in staged]
    store.set_content(job, "ig_carousel", media)
    return {"ok": True, "images": len(media), "media": media}


@app.post("/api/voices/preview")
async def voices_preview(
    request: Request,
    muse_voice: str = Form(""),
    voice: str = Form(""),
) -> FileResponse:
    """Preview a studio voice with fixed sample text."""
    user = require_user(request)
    from .pipeline import tts
    import uuid

    if not tts.narration_available():
        raise HTTPException(503, "Narration needs kokoro-onnx (or pocket-tts).")
    raw = (muse_voice or voice or "").strip()
    try:
        voice_id = tts.resolve_voice(raw or None)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    preview_dir = WORKSPACE_DIR / "voice_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:10]
    out_path = preview_dir / f"preview_{user.id}_{token}.wav"
    try:
        await asyncio.to_thread(tts.synthesize, VOICE_PREVIEW_TEXT, out_path, voice_id)
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {e}") from e
    return FileResponse(out_path, media_type="audio/wav", filename="voice-preview.wav")


# ------------------------------------------------------- cron / automation API --

def _cron_folders() -> list[dict]:
    """List automation_output paper folders and their artifacts.

    Merges durable ``history.json`` rows so published runs still appear after
    a folder delete, and every live folder gets an explicit ``status``.

    Skips internal dirs (e.g. ``topics`` prep cache) that are not video runs.
    """
    out: list[dict] = []
    root = _automation_output_dir()
    seen_ids: set[str] = set()
    # Not run folders — topic prep lives under automation_output/topics/.
    skip_dirs = {"topics", "__pycache__", "tmp", "temp"}
    hist_by_id: dict[str, dict] = {}
    try:
        for row in auto.load_history(root):
            fid = str(row.get("id") or "")
            if fid:
                hist_by_id[fid] = row
    except Exception:
        hist_by_id = {}

    if root.exists():
        for folder in sorted(root.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            if folder.name.startswith(".") or folder.name.lower() in skip_dirs:
                continue
            # Require a run signal so prep/cache dirs never pollute the queue.
            has_run = any(
                (folder / name).exists()
                for name in (
                    "paper.json", "paper.pdf", "published.json",
                    "checkpoint.json", "results.json",
                )
            ) or any(folder.glob("*.pdf")) or any(folder.glob("video*.mp4")) or (folder / "video").is_dir()
            if not has_run:
                continue
            entry: dict = {"id": folder.name, "artifacts": {}, "deleted": False}
            paper_json = folder / "paper.json"
            if paper_json.exists():
                try:
                    entry["paper"] = json.loads(paper_json.read_text(encoding="utf-8"))
                except Exception:
                    entry["paper"] = {}
            else:
                entry["paper"] = {}
            # Prefer a real video title over a weak folder/paper name.
            weak = {
                "", folder.name.lower(), "topics", "paper", "untitled", "overview",
            }
            cur_title = str((entry.get("paper") or {}).get("title") or "").strip()
            if cur_title.lower() in weak:
                for meta_rel in (
                    "video/metadata.json",
                    "metadata.json",
                    "video_metadata.json",
                    "reel/metadata.json",
                ):
                    mp = folder / meta_rel
                    if not mp.is_file():
                        continue
                    try:
                        meta = json.loads(mp.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    mt = str(meta.get("title") or meta.get("slide_title") or "").strip()
                    if mt and mt.lower() not in weak:
                        entry.setdefault("paper", {})["title"] = mt
                        break
            # Resolve PDF path (named file preferred over legacy paper.pdf).
            try:
                from .automation import sources as _auto_src
                pdf_path = _auto_src.resolve_pdf_path(folder, entry.get("paper") or {})
                if pdf_path.is_file():
                    entry["artifacts"]["pdf"] = pdf_path.name
                    entry.setdefault("paper", {})["pdf_file"] = pdf_path.name
            except Exception:
                if (folder / "paper.pdf").exists():
                    entry["artifacts"]["pdf"] = "paper.pdf"
            videos: list[str] = []
            for f in folder.rglob("*"):
                if not f.is_file():
                    continue
                rel = f.relative_to(folder).as_posix()
                name = f.name.lower()
                if name.endswith((".mp4", ".mov", ".webm")):
                    videos.append(rel)
                elif name.endswith((".png", ".jpg", ".jpeg", ".webp")) and "thumb" in name:
                    entry["artifacts"].setdefault("thumbnails", []).append(rel)
                elif name in {"presentation.html"} or name.endswith("_presentation.html"):
                    entry["artifacts"].setdefault("slides", []).append(rel)
                elif name in {"post.txt", "narration.txt"}:
                    entry["artifacts"].setdefault("posts", []).append(rel)
                elif name.endswith(".json") and name not in {"paper.json", "published.json", "checkpoint.json", "results.json"}:
                    entry["artifacts"].setdefault("meta", []).append(rel)
                elif "/audio/" in rel or rel.startswith("audio/"):
                    entry["artifacts"].setdefault("audio", []).append(rel)
            videos.sort(
                key=lambda r: (
                    0 if r.startswith("video/") or r.startswith("video_") else 1,
                    r,
                )
            )
            if videos:
                entry["artifacts"]["videos"] = videos
            thumbs = entry["artifacts"].get("thumbnails") or []
            if thumbs:
                thumbs.sort(
                    key=lambda r: (
                        0 if r.startswith("video/") or r.startswith("video_") else 1,
                        r,
                    )
                )
                entry["artifacts"]["thumbnail"] = thumbs[0]
            if (folder / "post.txt").exists():
                entry["artifacts"].setdefault("posts", [])
                if "post.txt" not in entry["artifacts"]["posts"]:
                    entry["artifacts"]["posts"].insert(0, "post.txt")
            if (folder / "results.json").exists():
                entry["artifacts"]["results"] = "results.json"
            entry["published"] = (folder / "published.json").exists()
            # Incomplete = PDF present but no video yet (stopped mid-run).
            has_vid = bool(entry["artifacts"].get("videos"))
            entry["incomplete"] = bool(entry["artifacts"].get("pdf")) and not has_vid
            if entry["incomplete"]:
                ck = folder / "checkpoint.json"
                if ck.is_file():
                    try:
                        entry["checkpoint"] = json.loads(ck.read_text(encoding="utf-8"))
                    except Exception:
                        entry["checkpoint"] = {}
            if entry["published"]:
                entry["status"] = "published"
            elif has_vid:
                entry["status"] = "ready"
            elif entry["incomplete"]:
                entry["status"] = "incomplete"
            else:
                entry["status"] = "processing"
            hist = hist_by_id.get(folder.name) or {}
            entry["archived"] = bool(hist.get("archived"))
            if hist.get("youtube"):
                entry["youtube"] = hist["youtube"]
            # Archived rows live in History, not the active queue.
            if entry["archived"] and entry["status"] in {"ready", "published", "incomplete"}:
                entry["status"] = entry["status"]  # keep real status; filter uses archived flag
            seen_ids.add(folder.name)
            out.append(entry)

    # Tombstones from history (published/archived rows kept after folder delete).
    for fid, row in hist_by_id.items():
        if fid in seen_ids:
            continue
        if fid.lower() in skip_dirs:
            continue
        is_pub = bool(row.get("published") or row.get("status") == "published")
        is_arch = bool(row.get("archived"))
        if not (is_pub or is_arch):
            continue
        out.append({
            "id": fid,
            "paper": row.get("paper") or {"title": fid},
            "artifacts": {},
            "published": is_pub,
            "incomplete": False,
            "deleted": bool(row.get("deleted")),
            "archived": is_arch,
            "status": "published" if is_pub else (row.get("status") or "ready"),
            "youtube": row.get("youtube") or {},
            "history_only": True,
        })
        seen_ids.add(fid)

    # Newest-ish: prefer live folders already reverse-sorted; append tombstones last
    # then re-sort by id (date-prefixed) descending.
    out.sort(key=lambda r: str(r.get("id") or ""), reverse=True)
    return out


@app.get("/api/admin/cron")
def admin_cron_list(request: Request) -> dict:
    require_admin(request)
    return {"runs": _cron_folders()}


@app.get("/api/admin/automation")
def admin_automation_status(request: Request) -> dict:
    """Current automation run state + schedule (for the admin dashboard)."""
    require_admin(request)
    return auto.status()


@app.get("/api/admin/automation/preview")
def admin_automation_preview(request: Request) -> dict:
    """Preview which paper PDF(s) the next run would process."""
    require_admin(request)
    return auto.preview()


@app.get("/api/admin/automation/topics")
def admin_automation_topics(request: Request, refresh: bool = False) -> dict:
    """Trending AI topics for the Cron input tab (auto-refreshes after ~1h)."""
    require_admin(request)
    from .automation import topics as topics_mod

    return topics_mod.list_trending(refresh=refresh)


class TopicPrepareRequest(BaseModel):
    topic_id: str = ""
    topic: str = ""


class TopicSelectRequest(BaseModel):
    topic_id: str
    selected: bool = True
    title: str = ""
    blurb: str = ""


class TopicSearchRequest(BaseModel):
    query: str


@app.post("/api/admin/automation/topics/search")
def admin_automation_topics_search(req: TopicSearchRequest, request: Request) -> dict:
    """Search HN / AI news for a topic query; returns up to 4 scored angles."""
    require_admin(request)
    from .automation import topics as topics_mod

    try:
        return topics_mod.search_topics(req.query)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        log.bind(task="auto-topics").error(f"search failed: {e}")
        raise HTTPException(500, f"Search failed: {e}") from e


@app.post("/api/admin/automation/topics/select")
def admin_automation_topics_select(req: TopicSelectRequest, request: Request) -> dict:
    """Persist topic selection in SQLite for data-wise tracking."""
    require_admin(request)
    from .automation import topics as topics_mod

    try:
        row = topics_mod.select_topic(
            req.topic_id,
            selected=bool(req.selected),
            title=req.title,
            blurb=req.blurb,
        )
        return {"ok": True, "topic": row}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/admin/automation/topics/prepare")
def admin_automation_topics_prepare(req: TopicPrepareRequest, request: Request) -> dict:
    """Prepare rich, citable content for a topic via Muse."""
    require_admin(request)
    from .automation import topics as topics_mod

    try:
        return topics_mod.prepare(topic_id=req.topic_id, topic=req.topic)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        log.bind(task="auto-topics").error(f"prepare failed: {e}")
        raise HTTPException(500, f"Prepare failed: {e}") from e


class TopicQueueRequest(BaseModel):
    topic_id: str
    video_format: str = "youtube_video"
    target_duration: int = 480
    video_theme: str = "snow"
    video_style: str = "whiteboard"
    force: bool = False


@app.post("/api/admin/automation/topics/queue")
def admin_automation_topics_queue(req: TopicQueueRequest, request: Request) -> dict:
    """Create a Studio job from prepared topic content and start rendering."""
    user = require_admin(request)
    from .automation import topics as topics_mod

    try:
        return topics_mod.queue_video_from_prep(
            req.topic_id,
            user_id=getattr(user, "id", "system") or "system",
            video_opts={
                "video_format": req.video_format,
                "target_duration": req.target_duration,
                "video_theme": req.video_theme,
                "video_style": req.video_style,
            },
            force=req.force,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Queue failed: {e}") from e


@app.post("/api/admin/automation/trigger")
async def admin_automation_trigger(request: Request) -> dict:
    """Manually start an automation run for selected pending papers (admin).

    Requires JSON body ``{"paper_ids": ["arxiv:…", …]}``. Incomplete folders
    are not auto-started — use Resume / Complete for those.
    """
    require_admin(request)
    paper_ids: list[str] = []
    try:
        body = await request.json()
        if isinstance(body, dict) and body.get("paper_ids"):
            paper_ids = [str(x) for x in body["paper_ids"] if str(x).strip()]
    except Exception:
        paper_ids = []
    if not paper_ids:
        raise HTTPException(
            400,
            "Select one or more pending papers to run. "
            "Incomplete folders use Resume / Complete — they never auto-start.",
        )
    started = auto.trigger("manual", paper_ids=paper_ids)
    if not started:
        raise HTTPException(409, "An automation run is already in progress")
    return {"ok": True, "status": auto.status(), "selected": paper_ids}


@app.post("/api/admin/automation/resume")
def admin_automation_resume(request: Request) -> dict:
    """Continue incomplete paper folders where a previous run stopped."""
    require_admin(request)
    incomplete = auto.list_incomplete()
    if not incomplete:
        raise HTTPException(404, "Nothing to resume — no incomplete paper folders")
    started = auto.resume()
    if not started:
        raise HTTPException(409, "An automation run is already in progress")
    return {"ok": True, "resuming": incomplete, "status": auto.status()}


@app.post("/api/admin/automation/pause")
def admin_automation_pause(request: Request) -> dict:
    """Pause the active run after the current paper finishes."""
    require_admin(request)
    return auto.cancel_run()


class AutomationJobAction(BaseModel):
    folder: str = ""
    paper_id: str = ""
    # skip: mark seen so similar/same paper won't re-queue
    # delete: remove folder (optional mark_seen)
    # complete: resume just this paper
    mark_seen: bool = False
    delete_folder: bool = False


@app.post("/api/admin/automation/delete")
def admin_automation_delete(req: AutomationJobAction, request: Request) -> dict:
    """Delete an automation job folder. Use mark_seen if it should not reappear."""
    require_admin(request)
    if not req.folder and not req.paper_id:
        raise HTTPException(400, "folder or paper_id is required")
    try:
        return auto.delete_job(req.folder, paper_id=req.paper_id, mark_seen=bool(req.mark_seen))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/admin/automation/skip")
def admin_automation_skip(req: AutomationJobAction, request: Request) -> dict:
    """Mark paper as already handled (similar/same already generated) — won't re-queue."""
    require_admin(request)
    try:
        return auto.skip_paper(
            req.paper_id,
            folder_name=req.folder,
            delete_folder=bool(req.delete_folder),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/admin/automation/complete")
def admin_automation_complete(req: AutomationJobAction, request: Request) -> dict:
    """Complete / resume one specific incomplete paper."""
    require_admin(request)
    try:
        return auto.complete_paper(paper_id=req.paper_id, folder_name=req.folder)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


class AutomationToggle(BaseModel):
    enabled: bool


@app.post("/api/admin/automation/toggle")
def admin_automation_toggle(req: AutomationToggle, request: Request) -> dict:
    """Enable/disable the scheduled automation (manual trigger still works)."""
    require_admin(request)
    get_settings().auto_enabled = req.enabled
    log.bind(task="auto").info(f"scheduler {'enabled' if req.enabled else 'disabled'} by admin")
    return {"ok": True, "status": auto.status()}


@app.get("/api/admin/runtime-settings")
def admin_runtime_settings_get(request: Request) -> dict:
    """Current LLM / thumbnail backend selection (admin dashboard)."""
    require_admin(request)
    from . import runtime_settings as rs

    return rs.current()


class RuntimeSettingsUpdate(BaseModel):
    llm_provider: str = ""
    muse_model: str = ""
    muse_vision_model: str = ""
    thumbnail_backend: str = ""
    auto_video_style: str = ""
    auto_video_theme: str = ""


@app.put("/api/admin/runtime-settings")
def admin_runtime_settings_put(req: RuntimeSettingsUpdate, request: Request) -> dict:
    """Admin selects the Muse text model for cron and jobs."""
    require_admin(request)
    from . import runtime_settings as rs

    payload = {k: v for k, v in req.model_dump().items() if str(v or "").strip()}
    try:
        snap = rs.save(payload)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "settings": snap, "status": auto.status()}


@app.post("/api/admin/cron/{folder}/delete")
def admin_cron_delete(folder: str, request: Request, mark_seen: bool = False) -> dict:
    """Delete a cron/automation output folder from the history list."""
    require_admin(request)
    try:
        return auto.delete_job(folder, mark_seen=mark_seen)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/admin/cron/{folder}/archive")
def admin_cron_archive(folder: str, request: Request, archived: bool = True) -> dict:
    """Move a run to History (archived) or restore it to the active filters."""
    require_admin(request)
    try:
        return auto.archive_job(folder, archived=archived)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/admin/cron/{folder}/file/{path:path}")
def admin_cron_file(folder: str, path: str, request: Request):
    require_admin(request)
    root = _automation_output_dir().resolve()
    base = _safe_cron_dir(folder)
    target = (base / path).resolve()
    if not base.is_relative_to(root):
        raise HTTPException(403, "Forbidden")
    if base not in target.parents and target != base:
        raise HTTPException(403, "Forbidden")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(
        target,
        filename=target.name,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


class PublishCronRequest(BaseModel):
    title: str = ""
    description: str = ""


@app.post("/api/admin/cron/{folder}/publish")
def admin_cron_publish(folder: str, req: PublishCronRequest, request: Request) -> dict:
    """Mark an automation run as reviewed + publish it.

    Actual YouTube upload requires client_secrets.json; when unavailable this
    records the review decision so the run is flagged as published/approved.
    Prefers long-form ``video/video.mp4`` (not the reel) and fills title /
    description from ``video/metadata.json`` when the request body is empty.
    """
    require_admin(request)
    base = _safe_cron_dir(folder)
    if not base.exists() or not base.is_dir():
        raise HTTPException(404, "Run not found")
    caps = detect_capabilities()
    meta = _load_cron_publish_meta(base)
    title = (req.title or meta.get("title") or folder).strip()
    description = (req.description or meta.get("description") or "").strip()
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else None
    record = {
        "reviewed_at": _time.time(),
        "title": title,
        "description": description,
        "tags": tags or [],
        "youtube_available": bool(caps.youtube),
    }
    yt_result = None
    if caps.youtube:
        try:
            from .pipeline import publish as _publish
            video = _prefer_cron_video(base)
            thumb = _prefer_cron_thumb(base)
            if video:
                yt_result = _publish.upload_to_youtube(
                    video_path=video,
                    title=title,
                    description=description,
                    thumbnail=thumb,
                    tags=tags,
                )
                record["youtube"] = yt_result
                record["video"] = video.relative_to(base).as_posix()
        except Exception as e:  # best-effort — never 500 the review
            record["error"] = str(e)
            log.bind(task="cron").warning(f"cron publish failed for {folder}: {e}")
    try:
        auto.mark_folder_published(base, record)
    except Exception:
        (base / "published.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    log.bind(task="cron").info(f"cron run {folder} published (youtube={bool(yt_result)})")
    return {"ok": True, "published": record}


@app.get("/api/capabilities")
def capabilities(refresh: bool = False) -> dict:
    from .pipeline import tts

    caps = detect_capabilities(refresh=refresh).dict()
    caps["runner"] = runner.stats()
    caps["muse_tts"] = tts.narration_available()
    caps["muse_tts_model"] = "narration"
    try:
        caps["voice_default_label"] = f"Voice · {tts.default_voice()}"
    except ValueError:
        caps["voice_default_label"] = "Studio voice"
    from .pipeline import thumbnail as thumb_mod

    tb = thumb_mod.probe_backends()
    from . import disk_store

    caps.update({
        "storage": disk_store.status(),
        "thumbnail_backend": get_settings().thumbnail_backend,
        "muse_image_model": get_settings().muse_image_model,
        "nano_banana": tb.get("nano_banana"),
        "nano_banana_reason": tb.get("nano_banana_reason"),
        "image_available": tb.get("any_image"),
        "slide_ai_images_default": get_settings().slide_ai_images_default,
        "scenarios": [],
    })
    return caps


class MediaTestImageRequest(BaseModel):
    prompt: str = ""
    width: int = 1280
    height: int = 720
    backend: str = "auto"  # auto | nano_banana
    scenario: str = ""
    image_b64: str = ""


@app.get("/api/media/status")
def media_status(refresh: bool = False) -> dict:
    """Muse Image thumbnail backend status for the image lab."""
    from .pipeline import thumbnail as thumb_mod

    tb = thumb_mod.probe_backends()
    s = get_settings()
    return {
        "thumbnail_backend": s.thumbnail_backend,
        "generate_thumbnail": s.generate_thumbnail,
        "backends": tb,
        "scenarios": [],
        "models": {
            "nano_banana": s.muse_image_model,
        },
        "slide_ai_images_default": s.slide_ai_images_default,
        "install_hint": (
            ""
            if tb.get("nano_banana")
            else "Thumbnails: Muse Image needs MODEL_API_KEY. Local image models are not installed right now."
        ),
    }


@app.get("/api/storage/status")
def storage_status_endpoint() -> dict:
    """Where jobs, costs, and memory are saved. Always the local SQLite files."""
    from . import disk_store

    return disk_store.status()


@app.post("/api/media/test-image")
def media_test_image(req: MediaTestImageRequest, request: Request) -> dict:
    """Generate a test thumbnail via Nano Banana — does not affect pipeline jobs."""
    import base64
    import tempfile

    require_user(request)
    from .pipeline import thumbnail as thumb_mod

    backend = (req.backend or "auto").strip().lower()
    raw_prompt = (req.prompt or "").strip()
    prompt = raw_prompt or thumb_mod.build_nano_banana_prompt(
        "Test image", "Multimodal Studio"
    )

    with tempfile.TemporaryDirectory(prefix="media_test_") as tmp:
        out = Path(tmp) / "test.png"
        path, msg = thumb_mod.generate_thumbnail(
            "Test image",
            "Multimodal Studio",
            out,
            prompt_override=prompt,
            backend_override=backend,
        )
        used = "nano_banana"
        if path is None or not path.is_file():
            return {"ok": False, "message": msg or "Image generation failed.", "backend": used}
        raw = path.read_bytes()
        return {
            "ok": True,
            "message": msg,
            "backend": used,
            "scenario": (req.scenario or "").strip() or None,
            "image_b64": base64.b64encode(raw).decode("ascii"),
            "mime": "image/png",
        }


@app.get("/api/video-formats")
def video_formats() -> dict:
    """Public catalog for the Studio pickers (formats, themes, layouts)."""
    from .video_options import PLATFORM_FORMAT_HINTS, THEME_ALIASES

    payload = {
        "formats": public_video_formats(),
        "themes": [],
        "styles": [],
        "style_categories": [],
        "visual_presets": [],
        "platform_formats": dict(PLATFORM_FORMAT_HINTS),
        "theme_aliases": dict(THEME_ALIASES),
    }
    # Formats must always ship even if a style/theme helper throws.
    try:
        payload["themes"] = public_video_themes()
        payload["styles"] = public_video_styles()
        payload["style_categories"] = public_style_categories()
        payload["visual_presets"] = public_visual_presets()
    except Exception:
        log.bind(task="video-formats").exception("style/theme catalog failed")
    return payload


@app.get("/api/style-preview", response_class=HTMLResponse)
def style_preview(
    style: str = "whiteboard", theme: str = "snow", fmt: str = "youtube_video",
) -> HTMLResponse:
    """Real render of a sample lesson in this style, for the picker preview.

    Same ``render_slideshow_html`` the video pipeline films, so the picker and
    the finished video cannot drift apart.
    """
    from .pipeline.sample_deck import render_sample

    try:
        html = render_sample(style, theme, fmt)
    except Exception:
        log.bind(task="style-preview").exception("sample render failed")
        return HTMLResponse("<p>Preview unavailable.</p>", status_code=500)
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=300"})


@app.get("/api/audience")
def audience_catalog() -> dict:
    """Age groups, knowledge levels, and the custom prompts they load."""
    from .pipeline.audience import catalog

    return catalog()


@app.post("/api/jobs/plan")
async def plan_job_topics(
    request: Request,
    file: UploadFile,
    video_format: str = Form("youtube_video"),
    video_theme: str = Form("snow"),
    video_style: str = Form("whiteboard"),
    target_duration: int = Form(480),
    content_layout: str = Form("auto"),
    age_group: str = Form("auto"),
    knowledge_level: str = Form("auto"),
    custom_prompt: str = Form(""),
    review_notes: str = Form(""),
    extra_topics: str = Form(""),
    muse_voice: str = Form(""),
    enable_web_research: str = Form("false"),
) -> dict:
    """Extract a large upload and classify it into selectable video topics."""
    from . import batch_jobs
    from .pipeline import tts as tts_mod
    from .pipeline.audience import stamp_options
    from .video_options import normalize_video_options

    user = require_user(request)
    fname = file.filename or ""
    suffix = Path(fname).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            400,
            "Unsupported file. Upload a document (PDF, Word, PowerPoint, TXT, "
            "Markdown, HTML, EPUB, CSV, Excel) or an image (PNG, JPG, WEBP, GIF, TIFF).",
        )
    data = await _read_upload_capped(file, STUDIO_UPLOAD_MAX_BYTES)
    if not data:
        raise HTTPException(400, "That file is empty.")
    video_opts = normalize_video_options(
        video_format=video_format,
        target_duration=target_duration,
        video_theme=video_theme,
        video_style=video_style,
    )
    video_opts["content_layout"] = (content_layout or "auto").strip() or "auto"
    style_key = str(video_opts.get("video_style") or "").strip().lower()
    if style_key and style_key != "auto":
        video_opts["lock_visual_preset"] = True
    else:
        video_opts.pop("lock_visual_preset", None)
    want_web = str(enable_web_research or "").strip().lower() in {"1", "true", "yes", "on"}
    video_opts["enable_web_research"] = want_web
    video_opts["extra_topics"] = (extra_topics or "").strip()
    try:
        video_opts["muse_voice"] = tts_mod.resolve_voice(muse_voice or None)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    video_opts = stamp_options(
        video_opts,
        age_group=age_group,
        knowledge_level=knowledge_level,
        custom_prompt=custom_prompt,
        review_notes=review_notes,
    )
    try:
        result = await asyncio.to_thread(
            batch_jobs.create_plan_job,
            filename=fname,
            data=data,
            user_id=user.id,
            options=video_opts,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.bind(task="job").error(f"plan topics failed: {e}")
        raise HTTPException(500, f"Topic planning failed: {e}") from e


@app.get("/api/jobs/{job_id}/topics")
def get_job_topics(request: Request, job_id: str) -> dict:
    from . import batch_jobs

    user = require_user(request)
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    plan = batch_jobs.get_plan(job_id)
    if not plan:
        raise HTTPException(404, "No topic plan on this job — run Plan topics first")
    return plan


@app.post("/api/jobs/{job_id}/topics")
async def reclassify_job_topics(request: Request, job_id: str) -> dict:
    from . import batch_jobs

    user = require_user(request)
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return await asyncio.to_thread(
            batch_jobs.reclassify_plan,
            job_id,
            max_topics=int(body.get("max_topics") or 80),
        )
    except FileNotFoundError:
        raise HTTPException(404, "Plan not found")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Reclassify failed: {e}") from e


@app.post("/api/jobs/from-plan")
async def create_jobs_from_plan(request: Request) -> dict:
    """Create one or many videos from a topic plan + selection."""
    from . import batch_jobs

    user = require_user(request)
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    plan_id = (body.get("plan_id") or body.get("job_id") or "").strip()
    if not plan_id:
        raise HTTPException(400, "plan_id is required")
    parent = store.get(plan_id)
    if not parent:
        raise HTTPException(404, "Plan not found")
    selected = body.get("selected_ids") or body.get("topics") or []
    if isinstance(selected, str):
        selected = [s.strip() for s in selected.split(",") if s.strip()]
    video_opts = {
        "video_format": body.get("video_format") or parent.options.get("video_format"),
        "video_theme": body.get("video_theme") or parent.options.get("video_theme"),
        "video_style": body.get("video_style") or parent.options.get("video_style"),
        "target_duration": body.get("target_duration")
        if body.get("target_duration") is not None
        else parent.options.get("target_duration"),
    }
    # Narration voice and publish flags travel with the plan or this request.
    if body.get("muse_voice"):
        video_opts["muse_voice"] = str(body.get("muse_voice")).strip()
    elif parent.options.get("muse_voice"):
        video_opts["muse_voice"] = parent.options.get("muse_voice")
    if "publish" in body:
        video_opts["publish"] = bool(body.get("publish"))
    elif "publish" in (parent.options or {}):
        video_opts["publish"] = bool(parent.options.get("publish"))
    if "slide_ai_images" in body:
        video_opts["slide_ai_images"] = bool(body.get("slide_ai_images"))
    elif "slide_ai_images" in (parent.options or {}):
        video_opts["slide_ai_images"] = bool(parent.options.get("slide_ai_images"))
    try:
        result = await asyncio.to_thread(
            batch_jobs.create_jobs_from_plan,
            plan_id,
            user_id=user.id,
            selected_ids=list(selected),
            mode=str(body.get("mode") or "per_topic"),
            video_opts=video_opts,
            enable_web_research=bool(body.get("enable_web_research", True)),
            deep_grounding=bool(body.get("deep_grounding", True)),
            content_layout=str(
                body.get("content_layout")
                or parent.options.get("content_layout")
                or "auto"
            ),
            extra_topics=str(body.get("extra_topics") or ""),
            age_group=str(body.get("age_group") or parent.options.get("age_group") or "auto"),
            knowledge_level=str(
                body.get("knowledge_level") or parent.options.get("knowledge_level") or "auto"
            ),
            custom_prompt=str(
                body.get("custom_prompt")
                if body.get("custom_prompt") is not None
                else parent.options.get("custom_prompt") or ""
            ),
            review_notes=str(body.get("review_notes") or parent.options.get("review_notes") or ""),
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.bind(task="job").error(f"from-plan failed: {e}")
        raise HTTPException(500, f"Failed to create videos from plan: {e}") from e


@app.post("/api/jobs")
async def create_job(
    request: Request,
    file: UploadFile,
    publish: bool = Form(False),
    target_duration: int = Form(480),
    video_format: str = Form("youtube_video"),
    video_theme: str = Form("snow"),
    video_style: str = Form("whiteboard"),
    youtube_video_url: str = Form(""),
    extra_topics: str = Form(""),
    enable_web_research: str = Form("false"),
    slide_ai_images: str = Form("false"),
    muse_voice: str = Form(""),
    content_layout: str = Form("auto"),
    age_group: str = Form("auto"),
    knowledge_level: str = Form("auto"),
    custom_prompt: str = Form(""),
    review_notes: str = Form(""),
) -> dict:
    fname = file.filename or ""
    suffix = Path(fname).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            400,
            "Unsupported file. Upload a document (PDF, Word, PowerPoint, TXT, "
            "Markdown, HTML, EPUB) or an image (PNG, JPG, WEBP, GIF, TIFF).",
        )

    video_opts = normalize_video_options(
        video_format=video_format,
        target_duration=target_duration,
        youtube_video_url=youtube_video_url,
        video_theme=video_theme,
        video_style=video_style,
    )
    # Lock only when the user picked an explicit style (theme alone must not
    # freeze video_style=auto).
    style_key = str(video_opts.get("video_style") or "").strip().lower()
    if style_key and style_key != "auto":
        video_opts["lock_visual_preset"] = True

    from .pipeline import tts as tts_mod

    try:
        voice_opts = {"muse_voice": tts_mod.resolve_voice(muse_voice or None)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    user = require_user(request)
    data = await _read_upload_capped(file, STUDIO_UPLOAD_MAX_BYTES)
    if not data:
        raise HTTPException(400, "That file is empty.")
    want_slide_ai = str(slide_ai_images or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    want_web_research = str(enable_web_research or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    from .pipeline.audience import stamp_options

    job_opts = stamp_options(
        {
            "publish": publish,
            "extra_topics": (extra_topics or "").strip(),
            # Force live web research even for uploaded documents (user opt-in).
            "enable_web_research": want_web_research,
            # Experimental — stored for future slide image injection after Image lab QA.
            "slide_ai_images": want_slide_ai,
            **voice_opts,
            **video_opts,
            "content_layout": (content_layout or "auto").strip() or "auto",
        },
        age_group=age_group,
        knowledge_level=knowledge_level,
        custom_prompt=custom_prompt,
        review_notes=review_notes,
    )
    job = store.create(
        fname,
        options=job_opts,
        user_id=user.id,
    )
    from .workspace_store import resolve_job_dir

    work = resolve_job_dir(job.id, create=True)
    try:
        dest = work / ("input" + suffix)
        await asyncio.to_thread(dest.write_bytes, data)

        runner.submit(run_pipeline, job)
        caps = detect_capabilities()
        log.bind(task="job").info(
            f"created {job.id} [{fname}] provider={caps.provider} llm={caps.llm} "
            f"vlm={caps.vlm} tts={caps.tts_engine} fmt={video_format} target={target_duration}s"
            f" voice={job.options.get('muse_voice') or ''}"
        )
        return {"id": job.id}
    except HTTPException:
        store.delete(job.id)
        shutil.rmtree(work, ignore_errors=True)
        raise
    except Exception:
        store.delete(job.id)
        shutil.rmtree(work, ignore_errors=True)
        raise


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    job = _job_for_user(request, job_id)
    return store.snapshot(job)


@app.get("/api/jobs/{job_id}/agent-trace")
def get_job_agent_trace(job_id: str, request: Request) -> dict:
    """Return the step-by-step agentic execution trace and run receipt."""
    job = _job_for_user(request, job_id)
    receipt = job.content.get("agent_receipt") or {}
    from .workspace_store import resolve_job_dir

    work = resolve_job_dir(job_id, create=False)
    trace_path = work / "agent_trace.jsonl"
    lines = []
    if trace_path.exists():
        try:
            lines = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception:
            pass
    return {
        "job_id": job_id,
        "receipt": receipt,
        "traces": lines or receipt.get("steps", []),
    }


class AgentMemoryPost(BaseModel):
    key: str
    value: Any
    namespace: str = "general"
    tags: str = ""


@app.get("/api/agent/memory")
def get_agent_memory(request: Request, query: str = "", namespace: str = "") -> dict:
    """Inspect or search the persistent agent harness memory."""
    user = require_user(request)
    from .agent_memory import get_harness_memory

    mem = get_harness_memory()
    if query:
        items = mem.recall(query, namespace=namespace or None, limit=10)
    else:
        items = []
        for ns in mem.list_namespaces():
            items.extend(mem.recall("", namespace=ns, limit=5))
    return {
        "count": mem.count(),
        "namespaces": mem.list_namespaces(),
        "items": items,
    }


@app.post("/api/agent/memory")
def post_agent_memory(req: AgentMemoryPost, request: Request) -> dict:
    """Store or update a learned preference, style rule, or domain fact in agent memory."""
    user = require_user(request)
    from .agent_memory import get_harness_memory

    mem = get_harness_memory()
    mem.store(key=req.key, value=req.value, namespace=req.namespace, tags=req.tags)
    return {"status": "ok", "key": req.key, "namespace": req.namespace}


class RunToolRequest(BaseModel):
    tool_name: str
    args: dict[str, Any] = {}


@app.get("/api/agent/tools")
def get_agent_tools(request: Request) -> dict:
    """Return the registered tools catalog and schema in the Agent Harness."""
    user = require_user(request)
    from .agent_memory import get_harness_memory
    from .pipeline.agent_harness import AgentHarness

    from . import disk_store

    harness = AgentHarness(session_id="catalog_inspector")
    mem = get_harness_memory()
    return {
        "tools": harness.tools.get_catalog(),
        "max_turns": harness.max_turns,
        "memory_count": mem.count(),
        "memory_namespaces": mem.list_namespaces(),
        "memory_backend": mem.backend(),
        "storage": disk_store.status(),
    }


@app.post("/api/agent/run-tool")
def run_agent_tool(req: RunToolRequest, request: Request) -> dict:
    """Execute a single harness tool on demand with parameter validation."""
    user = require_user(request)
    from .pipeline.agent_harness import AgentHarness

    harness = AgentHarness(session_id=f"tool_exec_{int(_time.time())}")
    res = harness.tools.execute(req.tool_name, **req.args)
    return res.to_dict()


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, request: Request) -> dict:
    """Remove a session from history and delete its workspace folder."""
    job = _job_for_user(request, job_id)
    if job.busy:
        raise HTTPException(409, "Cannot delete a session while it is running")
    from .workspace_store import resolve_job_dir

    work = resolve_job_dir(job_id, create=False)
    store.delete(job_id)
    removed_local = False
    if work.is_dir():
        shutil.rmtree(work, ignore_errors=True)
        removed_local = not work.exists()
    # Legacy bare-id folder
    legacy = WORKSPACE_DIR / job_id
    if legacy.is_dir() and legacy.resolve() != work.resolve():
        shutil.rmtree(legacy, ignore_errors=True)
    return {"ok": True, "removed_local": removed_local}


@app.get("/api/sessions")
def list_sessions(request: Request) -> dict:
    """History of jobs (newest first). One local user, so every job is listed."""
    require_user(request)
    return {"sessions": store.list_jobs(user_id=None, admin=True)}


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    job = _job_for_user(request, job_id)

    q = store.subscribe(job_id)

    async def event_gen():
        # Send the current snapshot immediately so a late subscriber is in sync.
        yield f"data: {json.dumps(store.snapshot(job))}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Block in a worker thread so we don't tie up the event loop;
                    # short timeout doubles as a heartbeat + disconnect check.
                    snap = await asyncio.to_thread(q.get, True, 10)
                    yield f"data: {json.dumps(snap)}\n\n"
                except Exception:
                    yield ": ping\n\n"  # heartbeat keeps proxies/connections alive
        finally:
            store.unsubscribe(job_id, q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class ContentPatch(BaseModel):
    extracted_text: str | None = None
    narration: str | None = None
    extra_topics: str | None = None
    target_duration: int | None = None
    video_format: str | None = None
    video_theme: str | None = None
    video_style: str | None = None
    content_layout: str | None = None
    muse_voice: str | None = None
    youtube_video_url: str | None = None
    publish_title: str | None = None
    publish_description: str | None = None
    publish_tags: list[str] | None = None
    social_metadata: dict | None = None
    age_group: str | None = None
    knowledge_level: str | None = None
    custom_prompt: str | None = None
    review_notes: str | None = None


def _apply_job_voice_options(job, *, muse_voice: str | None = None) -> None:
    """Set the studio narration voice. Empty values are a no-op."""
    from .pipeline import tts as tts_mod

    raw = (muse_voice or "").strip()
    if not raw:
        return
    try:
        voice_id = tts_mod.resolve_voice(raw)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    for k in (
        "voice_preset",
        "pocket_voice",
        "voice_id",
        "voice_style_path",
        "cloud_voice_id",
    ):
        job.options.pop(k, None)
    job.options["muse_voice"] = voice_id


@app.patch("/api/jobs/{job_id}/content")
def patch_content(job_id: str, patch: ContentPatch, request: Request) -> dict:
    job = _job_for_user(request, job_id)
    if job.busy:
        raise HTTPException(409, "Cannot edit content while a run is in progress")
    user = require_user(request)
    if patch.extracted_text is not None:
        store.set_content(job, "extracted_text", patch.extracted_text)
    if patch.narration is not None:
        store.set_content(job, "narration", patch.narration)
    if patch.publish_title is not None:
        store.set_content(job, "publish_title", patch.publish_title.strip()[:100])
    if patch.publish_description is not None:
        store.set_content(job, "publish_description", patch.publish_description.strip())
    if patch.publish_tags is not None:
        tags = [str(t).strip().lower()[:30] for t in patch.publish_tags if str(t).strip()][:15]
        store.set_content(job, "publish_tags", tags)
    if patch.social_metadata is not None and isinstance(patch.social_metadata, dict):
        merged = dict(job.content.get("social_metadata") or {})
        merged.update(patch.social_metadata)
        store.set_content(job, "social_metadata", merged)
    if patch.extra_topics is not None:
        job.options["extra_topics"] = patch.extra_topics.strip()
        store.set_content(job, "extra_topics", patch.extra_topics.strip())
    if patch.content_layout is not None:
        layout = (patch.content_layout or "auto").strip().lower() or "auto"
        job.options["content_layout"] = layout
        store.set_content(job, "content_layout", layout)
    if (
        patch.age_group is not None
        or patch.knowledge_level is not None
        or patch.custom_prompt is not None
        or patch.review_notes is not None
    ):
        from .pipeline.audience import stamp_options

        stamped = stamp_options(
            job.options,
            age_group=patch.age_group if patch.age_group is not None else job.options.get("age_group"),
            knowledge_level=(
                patch.knowledge_level
                if patch.knowledge_level is not None
                else job.options.get("knowledge_level")
            ),
            custom_prompt=(
                patch.custom_prompt
                if patch.custom_prompt is not None
                else job.options.get("custom_prompt")
            ),
            review_notes=(
                patch.review_notes
                if patch.review_notes is not None
                else job.options.get("review_notes")
            ),
        )
        for key in (
            "age_group",
            "knowledge_level",
            "custom_prompt",
            "review_notes",
            "audience_prompt_source",
        ):
            if key in stamped:
                job.options[key] = stamped[key]
                store.set_content(job, key, stamped[key])
    if (patch.muse_voice or "").strip():
        _apply_job_voice_options(job, muse_voice=patch.muse_voice)
        store.set_content(job, "muse_voice", job.options.get("muse_voice") or "")
        for key in (
            "voice_preset",
            "pocket_voice",
            "voice_id",
            "voice_style_path",
            "cloud_voice_id",
        ):
            if key in (job.content or {}):
                store.set_content(job, key, "")
    if patch.target_duration is not None or patch.video_format is not None or patch.youtube_video_url is not None or patch.video_theme is not None or patch.video_style is not None:
        video_opts = normalize_video_options(
            video_format=patch.video_format or job.options.get("video_format"),
            target_duration=(
                patch.target_duration
                if patch.target_duration is not None
                else job.options.get("target_duration", 0)
            ),
            youtube_video_url=(
                patch.youtube_video_url
                if patch.youtube_video_url is not None
                else job.options.get("youtube_video_url", "")
            ),
            video_theme=(
                patch.video_theme
                if patch.video_theme is not None
                else job.options.get("video_theme")
            ),
            video_style=(
                patch.video_style
                if patch.video_style is not None
                else job.options.get("video_style")
            ),
        )
        job.options.update(video_opts)
        # Lock when style is explicit; Auto style must still be resolvable.
        style_key = str(video_opts.get("video_style") or "").strip().lower()
        if patch.video_style is not None or patch.video_theme is not None:
            if style_key and style_key != "auto":
                job.options["lock_visual_preset"] = True
            else:
                job.options.pop("lock_visual_preset", None)
        # normalize_video_options does not emit Auto flags — clear leftovers so a
        # prior Auto run cannot keep the UI stuck on "Auto → …" after a manual lock.
        for stale in (
            "video_style_was_auto",
            "video_theme_was_auto",
            "video_style_reason",
            "video_theme_reason",
        ):
            if stale not in video_opts:
                job.options.pop(stale, None)
        for key, value in video_opts.items():
            store.set_content(job, key, value)
    return store.snapshot(job)


class RunRequest(BaseModel):
    stage: str
    mode: str = "single"  # "single" | "from"


@app.post("/api/jobs/{job_id}/run")
def run_stage(job_id: str, req: RunRequest, request: Request) -> dict:
    job = _job_for_user(request, job_id)
    if req.stage not in STAGE_FUNCS:
        raise HTTPException(400, f"Unknown stage: {req.stage}")
    if job.busy:
        raise HTTPException(409, "A run is already in progress for this job")
    if req.mode == "from":
        runner.submit(run_from_stage, job, req.stage)
    else:
        runner.submit(run_single_stage, job, req.stage)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/script")
def get_script(job_id: str, request: Request) -> dict:
    """Per-slide narration scripts (for the in-UI voice recorder)."""
    job = _job_for_user(request, job_id)
    slides = job.content.get("slides") or []
    scripts = [
        ((s.get("narration") if isinstance(s, dict) else str(s)) or "").strip()
        for s in slides
    ]
    full = job.content.get("narration") or "\n\n".join(scripts).strip()
    return {"slides": scripts, "narration": full, "count": len(scripts)}


class ContentReviewRequest(BaseModel):
    notes: str | None = None
    narration: str | None = None


@app.post("/api/jobs/{job_id}/review-content")
def review_job_content(
    job_id: str,
    request: Request,
    body: ContentReviewRequest = ContentReviewRequest(),
) -> dict:
    """Re-check slides for duplicates and voice-sync issues (uses current edits)."""
    job = _job_for_user(request, job_id)
    from .pipeline.content_review import review_slides

    payload = body or ContentReviewRequest()
    notes = (payload.notes if payload.notes is not None else "") or str(
        job.options.get("review_notes") or ""
    )
    narr = payload.narration if payload.narration is not None else job.content.get("narration")
    review = review_slides(
        job.content.get("slides") or [],
        options=job.options,
        narration=narr or "",
        user_notes=notes,
    )
    store.set_content(job, "content_review", review)
    if payload.notes is not None:
        job.options["review_notes"] = notes.strip()[:1500]
        store.set_content(job, "review_notes", job.options["review_notes"])
    return {"ok": True, "review": review}


@app.post("/api/jobs/{job_id}/voice-recording")
async def upload_voice_recording(
    request: Request,
    job_id: str,
    slide_index: int = Form(-1),
    audio: UploadFile = File(...),
) -> dict:
    """Save a user voice recording as narration audio.

    ``slide_index >= 0`` saves the clip as that slide's narration; ``-1`` saves a
    whole-narration recording (split later is out of scope - it is used as slide 0
    when no per-slide clips exist). Files live under ``workspace/{id}/recorded/``.
    """
    job = _job_for_user(request, job_id)
    if job.busy:
        raise HTTPException(409, "Cannot upload recordings while a run is in progress")
    from .workspace_store import resolve_job_dir

    work = resolve_job_dir(job_id, create=True)
    rec_dir = work / "recorded"
    rec_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(audio.filename or "clip.webm").suffix.lower() or ".webm"
    name = f"slide_{slide_index:03d}{suffix}" if slide_index >= 0 else f"full{suffix}"
    dest = rec_dir / name
    data = await audio.read()
    await asyncio.to_thread(dest.write_bytes, data)

    recorded = dict(job.options.get("recorded_audio") or {})
    recorded[str(slide_index)] = dest.relative_to(work).as_posix()
    job.options["recorded_audio"] = recorded
    store.set_content(job, "recorded_audio", recorded)
    log.bind(task="voice").info(f"recorded clip saved for {job_id} slide={slide_index}")
    return {"ok": True, "path": dest.relative_to(work).as_posix()}


@app.post("/api/jobs/{job_id}/regenerate-metadata")
def regenerate_metadata(job_id: str, request: Request, scope: str = "all") -> dict:
    """Re-run publish_meta for title/description/tags (text only).

    Thumbnail generation is on-demand via ``/generate-thumbnail`` — never
    auto-run from this endpoint.
    """
    job = _job_for_user(request, job_id)
    if job.busy:
        raise HTTPException(409, "A run is already in progress for this job")
    if scope == "thumbnail":
        # Kept for older UI clients — route to the on-demand endpoint.
        return generate_thumbnail_api(job_id, request)
    for k in ("publish_title", "publish_description", "publish_tags"):
        store.set_content(job, k, None)
    runner.submit(run_single_stage, job, "publish_meta")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/generate-thumbnail")
def generate_thumbnail_api(job_id: str, request: Request) -> dict:
    """Generate a thumbnail on demand (Nano Banana Pro / local fallbacks)."""
    from .orchestrator import generate_job_thumbnail

    job = _job_for_user(request, job_id)
    if job.busy:
        raise HTTPException(409, "A run is already in progress for this job")
    # Clear previous so a fresh image is written.
    store.set_content(job, "thumbnail", None)
    if "thumbnail" in (job.artifacts or {}):
        arts = dict(job.artifacts)
        arts.pop("thumbnail", None)
        job.artifacts = arts
    ok, message = generate_job_thumbnail(job)
    if not ok:
        return {
            "ok": False,
            "message": message,
            "thumbnail": job.artifacts.get("thumbnail"),
        }
    return {
        "ok": True,
        "message": message,
        "thumbnail": job.artifacts.get("thumbnail"),
    }


class SocialMetaRequest(BaseModel):
    # Generate only the platforms the user selected (default: current tab).
    platforms: list[str] = ["youtube"]


@app.post("/api/jobs/{job_id}/social-metadata")
def social_metadata(job_id: str, req: SocialMetaRequest, request: Request) -> dict:
    """Generate per-platform title/description/hashtags for the selected socials.

    Merges into any existing ``social_metadata`` so regenerating one tab does
    not wipe the others. Reuses narration, slide outline, and already-generated
    platform titles as stored context.
    """
    job = _job_for_user(request, job_id)
    from . import costs
    from .pipeline import metadata as meta_gen

    title = job.content.get("publish_title") or job.content.get("title") or job.filename
    narration = job.content.get("narration") or ""
    slides = job.content.get("slides") or []
    outline_bits = []
    for s in slides[:24]:
        if not isinstance(s, dict):
            continue
        h = (s.get("heading") or "").strip()
        if h:
            outline_bits.append(f"- {h}")
    script_parts = []
    if outline_bits:
        script_parts.append("Slide outline:\n" + "\n".join(outline_bits))
    if narration:
        script_parts.append("Narration:\n" + narration)
    script = "\n\n".join(script_parts) or narration

    existing = dict(job.content.get("social_metadata") or {})
    other_bits = []
    yt_title = (job.content.get("publish_title") or "").strip()
    if yt_title and "youtube" not in (req.platforms or []):
        other_bits.append(f"youtube: {yt_title}")
    for k, v in existing.items():
        if not isinstance(v, dict):
            continue
        if k in (req.platforms or []):
            continue
        t = (v.get("title") or "").strip()
        if t:
            other_bits.append(f"{k}: {t}")
    extra = ""
    if other_bits:
        extra = (
            "Already generated for other tabs (keep tone/branding consistent; "
            "reuse facts, do not copy verbatim):\n" + "\n".join(other_bits[:12])
        )
    if job.content.get("doc_type"):
        extra = (extra + f"\nDoc type: {job.content.get('doc_type')}").strip()

    base_tags = job.content.get("publish_tags") or []
    platforms = req.platforms or []
    with costs.job_context(job.id):
        social, message = meta_gen.generate_social_metadata(
            title,
            script,
            platforms,
            base_tags,
            video_format=job.options.get("video_format"),
            extra_context=extra,
        )
    merged = dict(existing)
    merged.update(social or {})
    store.set_content(job, "social_metadata", merged)
    return {"social": merged, "message": message, "generated": list((social or {}).keys())}


@app.get("/files/{job_id}/{path:path}")
def get_file(job_id: str, path: str, request: Request):
    _job_for_user(request, job_id)
    from .workspace_store import resolve_job_dir

    # create=True so the job folder exists. Traversal checks still apply.
    base = resolve_job_dir(job_id, create=True).resolve()
    root = WORKSPACE_DIR.resolve()
    if not base.is_relative_to(root):
        raise HTTPException(403, "Forbidden")
    target = (base / path).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(403, "Forbidden")
    if not target.is_file():
        from . import blob_store

        if not blob_store.fetch(job_id, path, target):
            raise HTTPException(404, "File not found")

    import mimetypes

    media, _ = mimetypes.guess_type(str(target))
    if not media:
        media = "application/octet-stream"
    # HTML5 <video> needs a correct type + byte ranges to start without
    # buffering the whole file (long final.mp4 used to spin at 0:00).
    if target.suffix.lower() == ".mp4":
        media = "video/mp4"
    elif target.suffix.lower() in {".webm"}:
        media = "video/webm"
    elif target.suffix.lower() in {".mp3"}:
        media = "audio/mpeg"
    elif target.suffix.lower() in {".wav"}:
        media = "audio/wav"

    # Allow revalidation (ETag/mtime) instead of no-store so range requests can
    # resume; still bust via ?v= when the UI regenerates artifacts.
    headers = {
        "Cache-Control": "private, max-age=0, must-revalidate",
        "Accept-Ranges": "bytes",
    }
    return FileResponse(target, media_type=media, headers=headers)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(
            ico,
            media_type="image/x-icon",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    raise HTTPException(404, "favicon not found")


def _bust_static_html(html: str) -> str:
    """Append ASSET_VERSION to local /static asset URLs."""
    for name in (
        "styles.css", "app.js", "slide_kit.js",
        "chitti.js", "chitti.css",
        "favicon.svg", "favicon-256.png", "favicon.ico", "muse-mark.js",
    ):
        html = html.replace(f"/static/{name}", f"/static/{name}?v={ASSET_VERSION}")
    return html


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = _bust_static_html((STATIC_DIR / "index.html").read_text(encoding="utf-8"))
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )



@app.websocket("/ws/chitti/live")
async def chitti_live_ws(websocket: WebSocket):
    """C.H.I.T.T.I. voice — Muse Voice Transcribe in, Muse Wonder reply, studio voice out."""
    from . import live_audio

    await websocket.accept()
    user = LOCAL_USER

    product = "multimodal"
    session_id = (websocket.query_params.get("session_id") or "").strip()
    if not live_audio.live_available():
        await websocket.send_json(
            {"error": "Muse is unavailable — set MODEL_API_KEY."}
        )
        await websocket.close()
        return

    system = live_audio.chitti_system_prompt(product=product, session_hint="")
    try:
        await live_audio.serve_chitti(
            websocket,
            system=system,
            job_id=f"chitti:{product}:{session_id or user.id}",
        )
    except Exception as e:  # noqa: BLE001
        log.bind(task="chitti").error(f"chitti live ws failed: {e}")
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
