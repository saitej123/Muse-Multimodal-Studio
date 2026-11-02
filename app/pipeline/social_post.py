"""Post assembled video / images / captions to social platforms.

Modes:
  - ``video``   — upload final.mp4 + caption (YouTube, IG Reels, X, LinkedIn)
  - ``image``   — thumbnail or cover image + caption
  - ``carousel``— Instagram multi-image from resized slide frames

Credentials come from ``app.social_credentials``. Missing/unready platforms
return a clear error rather than raising.
"""
from __future__ import annotations

import json
import mimetypes
import shutil
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from ..logging_setup import log
from .. import social_credentials as creds

# Instagram feed / carousel preferred size
_IG_SIZE = (1080, 1080)


def _work_paths(job) -> tuple[Path, Path | None, Path | None, list[Path]]:
    """Resolve video, thumbnail, and slide image paths for a job."""
    from ..workspace_store import resolve_job_dir

    work = resolve_job_dir(job.id, create=False)
    video = work / "final.mp4"
    if not video.exists():
        video = work / "raw.mp4"
    video_path = video if video.exists() else None

    thumb_name = job.content.get("thumbnail")
    thumb = (work / thumb_name) if thumb_name else work / "thumbnail.png"
    thumb_path = thumb if thumb.exists() else None

    slides: list[Path] = []
    shots = work / "pages_shots"
    pages = work / "pages"
    for folder in (shots, pages):
        if folder.is_dir():
            for p in sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg")):
                slides.append(p)
            if slides:
                break
    # Post-finalize: cover image retained next to presentation.html
    if not slides:
        for name in ("cover.png", "cover.jpg", "cover.jpeg", "cover.webp"):
            c = work / name
            if c.is_file():
                slides = [c]
                break
    # Fallback: capture frames or thumbnail
    if not slides:
        frames = work / "frames"
        if frames.is_dir():
            slides = sorted(frames.glob("*.png"))[:20]
    if not slides and thumb_path is not None:
        slides = [thumb_path]
    return work, video_path, thumb_path, slides


def prepare_instagram_carousel(work: Path, slide_paths: list[Path], limit: int = 10) -> list[Path]:
    """Resize slide frames to Instagram square JPEGs under work/social/ig_carousel/."""
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow required for Instagram carousel images") from e

    out_dir = work / "social" / "ig_carousel"
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    for i, src in enumerate(slide_paths[:limit]):
        try:
            im = Image.open(src).convert("RGB")
            # Cover-fit into square
            w, h = im.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            im = im.crop((left, top, left + side, top + side))
            im = im.resize(_IG_SIZE, Image.Resampling.LANCZOS)
            dest = out_dir / f"slide_{i + 1:02d}.jpg"
            im.save(dest, "JPEG", quality=90, optimize=True)
            results.append(dest)
        except Exception as e:  # noqa: BLE001
            log.bind(task="social-post").warning(f"skip slide {src.name}: {e}")
    return results


def _caption_for(job, platform: str) -> tuple[str, str, list[str]]:
    social = (job.content.get("social_metadata") or {}).get(platform) or {}
    title = (
        social.get("title")
        or job.content.get("publish_title")
        or job.content.get("slide_title")
        or job.filename
        or "Post"
    )
    desc = social.get("description") or job.content.get("publish_description") or ""
    tags = social.get("hashtags") or job.content.get("publish_tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tag_line = " ".join("#" + t.lstrip("#") for t in tags if t)
    body = (desc or title).strip()
    if tag_line and tag_line not in body:
        body = f"{body}\n\n{tag_line}".strip()
    return str(title), body, list(tags)


def _http_json(method: str, url: str, *, headers: dict | None = None, data: dict | bytes | None = None, timeout: int = 120) -> dict:
    hdrs = {"User-Agent": "MultimodalStudio/1.0", **(headers or {})}
    body = None
    if isinstance(data, dict):
        body = json.dumps(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    elif isinstance(data, (bytes, bytearray)):
        body = data
    req = request.Request(url, data=body, headers=hdrs, method=method.upper())
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


def post_youtube(job, mode: str = "video") -> dict[str, Any]:
    from . import publish as yt

    cfg = creds.get_platform("youtube")
    work, video, thumb, _ = _work_paths(job)
    if mode == "image":
        raise RuntimeError("YouTube image-only posts are not supported — use video mode.")
    if not video:
        raise RuntimeError("No assembled video found.")
    title, description, tags = _caption_for(job, "youtube")
    privacy = str(cfg.get("privacy") or "").strip()
    # Temporary privacy override via settings if provided
    if privacy in ("public", "unlisted", "private"):
        from ..config import get_settings
        get_settings().youtube_privacy = privacy
    # Optional secrets path override
    path = str(cfg.get("client_secrets_path") or "").strip()
    if path:
        from ..config import get_settings
        get_settings().youtube_client_secrets = path
    result = yt.upload_to_youtube(
        video,
        title=title,
        description=description,
        tags=tags,
        thumbnail=thumb,
    )
    return {"ok": True, "platform": "youtube", "mode": "video", "result": result}


def post_instagram(job, mode: str = "carousel") -> dict[str, Any]:
    """Post via Instagram Graph API (Business/Creator account required).

    Modes:
      carousel — multi-image from slides (default for IG)
      image    — single thumbnail
      video    — Reels from final.mp4
    """
    cfg = creds.get_platform("instagram")
    token = str(cfg.get("access_token") or "").strip()
    ig_user = str(cfg.get("ig_user_id") or "").strip()
    if not token or not ig_user:
        raise RuntimeError("Instagram credentials missing — set access_token and ig_user_id in Admin → Social.")

    work, video, thumb, slides = _work_paths(job)
    _, caption, _ = _caption_for(job, "instagram")
    base = f"https://graph.facebook.com/v21.0/{ig_user}"

    # Graph API needs publicly reachable image URLs. We host files under the
    # job files path — for local/dev this often fails; we still create containers
    # and document the requirement. Prefer uploading via resumable if available.
    # Practical approach: create media with image_url pointing at a data host
    # isn't possible offline — use Instagram Content Publishing with locally
    # uploaded binaries via ``/media`` + hosted URL when the app is public.
    #
    # For now we stage files and attempt container creation using file URLs
    # under /files/{job}/… when PUBLIC_BASE_URL is set; otherwise return staged
    # paths so the user can download / post manually.

    from ..config import get_settings
    public_base = str(getattr(get_settings(), "public_base_url", "") or "").strip().rstrip("/")

    staged: list[Path] = []
    if mode == "carousel":
        if not slides:
            raise RuntimeError("No slide images available for Instagram carousel.")
        staged = prepare_instagram_carousel(work, slides)
        if not staged:
            raise RuntimeError("Failed to prepare Instagram carousel images.")
    elif mode == "image":
        src = thumb or (slides[0] if slides else None)
        if not src:
            raise RuntimeError("No thumbnail or slide image for Instagram image post.")
        staged = prepare_instagram_carousel(work, [src], limit=1)
    elif mode == "video":
        if not video:
            raise RuntimeError("No assembled video for Instagram Reel.")
    else:
        raise RuntimeError(f"Unknown Instagram mode: {mode}")

    if not public_base:
        # Stage only — return paths for the UI download / manual post.
        rel = [f"/files/{job.id}/social/ig_carousel/{p.name}" for p in staged] if staged else []
        if mode == "video" and video:
            rel = [f"/files/{job.id}/{video.name}"]
        return {
            "ok": True,
            "platform": "instagram",
            "mode": mode,
            "staged": True,
            "message": (
                "Instagram images prepared. Set PUBLIC_BASE_URL (public https origin) "
                "in .env so Graph API can fetch media, then click Post again — "
                "or download the staged images and post manually."
            ),
            "media": rel,
            "caption": caption,
        }

    def _public_url(path: Path) -> str:
        rel = path.relative_to(work).as_posix()
        return f"{public_base}/files/{job.id}/{rel}"

    if mode == "video":
        assert video is not None
        create = _http_json(
            "POST",
            f"{base}/media?" + parse.urlencode({
                "media_type": "REELS",
                "video_url": _public_url(video),
                "caption": caption[:2200],
                "access_token": token,
            }),
        )
        creation_id = create.get("id")
        if not creation_id:
            raise RuntimeError(f"Instagram Reel create failed: {create}")
        pub = _http_json(
            "POST",
            f"{base}/media_publish?" + parse.urlencode({
                "creation_id": creation_id,
                "access_token": token,
            }),
        )
        return {"ok": True, "platform": "instagram", "mode": "video", "result": pub, "caption": caption}

    if mode == "image" and len(staged) == 1:
        create = _http_json(
            "POST",
            f"{base}/media?" + parse.urlencode({
                "image_url": _public_url(staged[0]),
                "caption": caption[:2200],
                "access_token": token,
            }),
        )
        creation_id = create.get("id")
        if not creation_id:
            raise RuntimeError(f"Instagram image create failed: {create}")
        pub = _http_json(
            "POST",
            f"{base}/media_publish?" + parse.urlencode({
                "creation_id": creation_id,
                "access_token": token,
            }),
        )
        return {"ok": True, "platform": "instagram", "mode": "image", "result": pub, "caption": caption}

    # Carousel: children then parent
    child_ids = []
    for img in staged:
        child = _http_json(
            "POST",
            f"{base}/media?" + parse.urlencode({
                "image_url": _public_url(img),
                "is_carousel_item": "true",
                "access_token": token,
            }),
        )
        cid = child.get("id")
        if not cid:
            raise RuntimeError(f"Instagram carousel child failed: {child}")
        child_ids.append(cid)
    parent = _http_json(
        "POST",
        f"{base}/media?" + parse.urlencode({
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption[:2200],
            "access_token": token,
        }),
    )
    creation_id = parent.get("id")
    if not creation_id:
        raise RuntimeError(f"Instagram carousel parent failed: {parent}")
    pub = _http_json(
        "POST",
        f"{base}/media_publish?" + parse.urlencode({
            "creation_id": creation_id,
            "access_token": token,
        }),
    )
    return {
        "ok": True,
        "platform": "instagram",
        "mode": "carousel",
        "result": pub,
        "caption": caption,
        "images": len(staged),
    }


def post_x(job, mode: str = "video") -> dict[str, Any]:
    """Post text (+ optional media) to X. Requires OAuth1 user tokens for media."""
    cfg = creds.get_platform("x")
    title, caption, _ = _caption_for(job, "x")
    text = caption[:280] if caption else title[:280]
    work, video, thumb, slides = _work_paths(job)

    bearer = str(cfg.get("bearer_token") or "").strip()
    api_key = str(cfg.get("api_key") or "").strip()
    api_secret = str(cfg.get("api_secret") or "").strip()
    access = str(cfg.get("access_token") or "").strip()
    access_secret = str(cfg.get("access_token_secret") or "").strip()

    media_path: Path | None = None
    if mode == "image":
        media_path = thumb or (slides[0] if slides else None)
    elif mode == "video":
        media_path = video
    # carousel → first few images as single image for X (X doesn't do IG-style carousel the same way)
    elif mode == "carousel":
        media_path = thumb or (slides[0] if slides else None)

    if not (api_key and api_secret and access and access_secret) and not bearer:
        raise RuntimeError("Twitter/X credentials missing — configure in Admin → Social.")

    # Text-only via bearer when no media
    if media_path is None or not media_path.exists():
        if bearer:
            data = _http_json(
                "POST",
                "https://api.twitter.com/2/tweets",
                headers={"Authorization": f"Bearer {bearer}"},
                data={"text": text},
            )
            return {"ok": True, "platform": "x", "mode": "text", "result": data}
        raise RuntimeError("X post needs OAuth1 keys for media, or bearer token for text-only.")

    # Media upload requires OAuth1 — use requests-oauthlib if available, else instruct.
    try:
        from requests_oauthlib import OAuth1Session
    except ImportError:
        # Stage media + post text if bearer available
        if bearer:
            data = _http_json(
                "POST",
                "https://api.twitter.com/2/tweets",
                headers={"Authorization": f"Bearer {bearer}"},
                data={"text": text},
            )
            return {
                "ok": True,
                "platform": "x",
                "mode": "text",
                "result": data,
                "message": "Posted text only (install requests-oauthlib for media upload).",
                "media_staged": f"/files/{job.id}/{media_path.relative_to(work).as_posix()}",
            }
        raise RuntimeError("Install requests-oauthlib to upload media to X, or use bearer for text-only.")

    oauth = OAuth1Session(api_key, client_secret=api_secret, resource_owner_key=access, resource_owner_secret=access_secret)
    mime = mimetypes.guess_type(str(media_path))[0] or "application/octet-stream"
    media_category = "tweet_video" if media_path.suffix.lower() == ".mp4" else "tweet_image"
    # INIT
    total = media_path.stat().st_size
    init = oauth.post(
        "https://upload.twitter.com/1.1/media/upload.json",
        data={"command": "INIT", "total_bytes": total, "media_type": mime, "media_category": media_category},
        timeout=60,
    )
    if init.status_code >= 400:
        raise RuntimeError(f"X media INIT failed: {init.text[:400]}")
    media_id = init.json().get("media_id_string")
    # APPEND
    with media_path.open("rb") as f:
        seg = 0
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            app = oauth.post(
                "https://upload.twitter.com/1.1/media/upload.json",
                data={"command": "APPEND", "media_id": media_id, "segment_index": seg},
                files={"media": chunk},
                timeout=120,
            )
            if app.status_code >= 400:
                raise RuntimeError(f"X media APPEND failed: {app.text[:400]}")
            seg += 1
    fin = oauth.post(
        "https://upload.twitter.com/1.1/media/upload.json",
        data={"command": "FINALIZE", "media_id": media_id},
        timeout=60,
    )
    if fin.status_code >= 400:
        raise RuntimeError(f"X media FINALIZE failed: {fin.text[:400]}")

    tweet = oauth.post(
        "https://api.twitter.com/2/tweets",
        json={"text": text, "media": {"media_ids": [media_id]}},
        timeout=60,
    )
    if tweet.status_code >= 400:
        raise RuntimeError(f"X tweet failed: {tweet.text[:400]}")
    return {"ok": True, "platform": "x", "mode": mode, "result": tweet.json()}


def post_linkedin(job, mode: str = "video") -> dict[str, Any]:
    cfg = creds.get_platform("linkedin")
    token = str(cfg.get("access_token") or "").strip()
    author = str(cfg.get("organization_urn") or cfg.get("person_urn") or "").strip()
    if not token or not author:
        raise RuntimeError("LinkedIn credentials missing — set access_token and person/org URN in Admin → Social.")

    work, video, thumb, slides = _work_paths(job)
    title, caption, _ = _caption_for(job, "linkedin")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202405",
    }

    # Text-only UGC post (works without media upload complexity)
    if mode == "image" and not (thumb or slides):
        mode = "text"
    if mode in ("text",) or (mode == "video" and not video) or (mode == "image" and not thumb and not slides):
        body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": caption[:3000]},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        data = _http_json("POST", "https://api.linkedin.com/v2/ugcPosts", headers=headers, data=body)
        return {"ok": True, "platform": "linkedin", "mode": "text", "result": data}

    # For image/video: register upload → upload binary → create UGC with media
    media_path = video if mode == "video" and video else (thumb or (slides[0] if slides else None))
    if not media_path:
        raise RuntimeError("No media file for LinkedIn post.")

    recipe = "urn:li:digitalmediaRecipe:feedshare-video" if media_path.suffix.lower() == ".mp4" else "urn:li:digitalmediaRecipe:feedshare-image"
    reg = _http_json(
        "POST",
        "https://api.linkedin.com/v2/assets?action=registerUpload",
        headers=headers,
        data={
            "registerUploadRequest": {
                "recipes": [recipe],
                "owner": author,
                "serviceRelationships": [{
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }],
            }
        },
    )
    try:
        upload_mech = reg["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
        upload_url = upload_mech["uploadUrl"]
        asset = reg["value"]["asset"]
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"LinkedIn registerUpload failed: {reg}") from e

    mime = mimetypes.guess_type(str(media_path))[0] or "application/octet-stream"
    with media_path.open("rb") as f:
        binary = f.read()
    put_req = request.Request(
        upload_url,
        data=binary,
        headers={"Authorization": f"Bearer {token}", "Content-Type": mime},
        method="PUT",
    )
    try:
        with request.urlopen(put_req, timeout=300) as resp:
            resp.read()
    except error.HTTPError as e:
        raise RuntimeError(f"LinkedIn media upload failed: {e.read().decode()[:400]}") from e

    category = "VIDEO" if media_path.suffix.lower() == ".mp4" else "IMAGE"
    body = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": caption[:3000]},
                "shareMediaCategory": category,
                "media": [{
                    "status": "READY",
                    "description": {"text": title[:200]},
                    "media": asset,
                    "title": {"text": title[:200]},
                }],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    data = _http_json("POST", "https://api.linkedin.com/v2/ugcPosts", headers=headers, data=body)
    return {"ok": True, "platform": "linkedin", "mode": mode, "result": data}


_POSTERS = {
    "youtube": post_youtube,
    "instagram": post_instagram,
    "x": post_x,
    "linkedin": post_linkedin,
}


def post_to_platform(job, platform: str, mode: str = "auto") -> dict[str, Any]:
    platform = (platform or "").lower().strip()
    if platform not in _POSTERS:
        raise RuntimeError(f"Unsupported platform: {platform}")
    cfg = creds.get_platform(platform)
    if not cfg.get("enabled"):
        raise RuntimeError(f"{platform} posting is disabled — enable it in Admin → Social.")
    if not creds._platform_ready(platform, cfg):
        raise RuntimeError(f"{platform} credentials incomplete — configure in Admin → Social.")

    if mode in ("", "auto", None):
        mode = {
            "youtube": "video",
            "instagram": "carousel",
            "x": "video",
            "linkedin": "video",
        }.get(platform, "video")

    log.bind(task="social-post").info(f"posting {platform} mode={mode} job={job.id}")
    return _POSTERS[platform](job, mode=mode)


def auto_post_job(job) -> list[dict[str, Any]]:
    """Post to every platform with auto_post enabled. Best-effort; never raises."""
    results = []
    for platform in creds.platforms_for_auto_post():
        try:
            results.append(post_to_platform(job, platform, mode="auto"))
        except Exception as e:  # noqa: BLE001
            log.bind(task="social-post").warning(f"auto_post {platform} failed: {e}")
            results.append({"ok": False, "platform": platform, "error": str(e)})
    return results
