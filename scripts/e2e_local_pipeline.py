#!/usr/bin/env python3
"""End-to-end pipeline check. Requires MODEL_API_KEY. Text model is Muse Wonder."""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force local stack before Settings loads
os.environ["LLM_PROVIDER"] = "muse"
os.environ["VLM_MAX_PAGES"] = "4"
os.environ["ANIMATION_MODE"] = "still"
os.environ["VIDEO_QUALITY"] = "1080p"
os.environ["GENERATE_THUMBNAIL"] = "true"
os.environ["THUMBNAIL_BACKEND"] = "auto"

from app.config import WORKSPACE_DIR, get_settings

get_settings.cache_clear()

from app.automation.sources import _fetch_arxiv
from app.jobs import store
from app.capabilities import detect_capabilities, clear_capabilities_cache
from app.orchestrator import run_pipeline
from app.video_options import normalize_video_options

_UA = {"User-Agent": "multimodal-studio-e2e/1.0"}


def main() -> int:
    clear_capabilities_cache()
    caps = detect_capabilities(refresh=True)
    s = get_settings()
    print("=== config ===")
    print(f"provider: {s.active_provider}  model: {s.llm_text_model}")
    print(f"thumbnail: {s.thumbnail_backend}")
    print(f"caps: llm={caps.llm} vlm={caps.vlm} tts={caps.tts_engine} playwright={caps.playwright}")
    if s.active_provider != "muse" or not caps.llm:
        print("FAIL: Muse is not active (set MODEL_API_KEY)")
        return 1

    print("\n=== latest arXiv paper ===")
    papers = _fetch_arxiv(["cs.LG", "cs.CL", "cs.CV", "cs.AI"], 3, keywords="")
    if not papers:
        print("FAIL: no papers fetched")
        return 1
    paper = next((p for p in papers if p.has_code), papers[0])
    print(f"title: {paper.title[:100]}")
    print(f"id: {paper.id}  code: {paper.code_url or 'none'}")
    print(f"pdf: {paper.pdf_url}")

    out_dir = ROOT / "automation_output" / f"e2e_local_{paper.id.split(':')[-1]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "paper.pdf"
    if not pdf_path.exists() or pdf_path.stat().st_size < 1024:
        print("\n=== downloading PDF ===")
        req = urllib.request.Request(paper.pdf_url, headers=_UA)
        with urllib.request.urlopen(req, timeout=120) as resp:
            pdf_path.write_bytes(resp.read())
    print(f"pdf size: {pdf_path.stat().st_size // 1024} KB")

    video_opts = normalize_video_options(
        video_format="youtube_video",
        target_duration=75,
        video_theme="default",
        video_style="default",
    )
    print("\n=== creating job ===")
    job = store.create(
        pdf_path.name,
        options={
            "publish": False,
            "extra_topics": "core method and results",
            **video_opts,
        },
        user_id="e2e-test",
    )
    work = WORKSPACE_DIR / job.id
    work.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf_path, work / "input.pdf")
    print(f"job_id: {job.id}")

    print("\n=== running full pipeline (Muse Wonder) ===")
    run_pipeline(job)

    print("\n=== result ===")
    print(f"status: {job.status}")
    if job.error:
        print(f"error: {job.error}")
    arts = job.artifacts or {}
    content = job.content or {}
    thumb = content.get("thumbnail") or (Path(arts.get("thumbnail", "")).name if arts.get("thumbnail") else "")
    report = {
        "job_id": job.id,
        "status": job.status,
        "error": job.error,
        "provider": s.active_provider,
        "paper": paper.title,
        "paper_id": paper.id,
        "video": arts.get("video_final"),
        "thumbnail": thumb,
        "publish_title": content.get("publish_title"),
        "stages": [{"key": st.key, "status": st.status.value, "detail": (st.detail or "")[:120]} for st in job.stages],
    }
    (out_dir / "e2e_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if job.status != "done":
        return 1
    if thumb:
        tp = work / thumb
        print(f"thumbnail file: {tp} exists={tp.exists()} size={tp.stat().st_size if tp.exists() else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
