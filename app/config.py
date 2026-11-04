"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BASE_DIR / "workspace"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Blank KEY= lines in .env must not wipe typed defaults (ints, bools).
        env_ignore_empty=True,
    )

    # ---------------------------------------------------------------- LLM ----
    # Text, vision, and images use the Meta Model API. Older provider values
    # (muse / ollama / openai / auto) are treated as Muse.
    llm_provider: str = "muse"

    # Bearer token for https://api.meta.ai/v1. MODEL_API_KEY still works.
    model_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("MODEL_API_KEY"),
    )
    # Slides, vision, and assistant replies. https://dev.meta.ai/docs/models
    muse_model: str = Field(
        default="muse-wonder-1.0",
        validation_alias=AliasChoices("MUSE_MODEL"),
    )
    muse_vision_model: str = Field(
        default="muse-wonder-1.0",
        validation_alias=AliasChoices("MUSE_VISION_MODEL"),
    )
    # High-volume topic briefs. Same Responses API, lower token price.
    muse_lite_model: str = Field(
        default="muse-spark-1.3",
        validation_alias=AliasChoices("MUSE_LITE_MODEL"),
    )
    # Interview Prep vision. Empty = muse_lite_model.
    interview_vlm_model: str = ""
    # C.H.I.T.T.I. reply model. Listening is Muse Voice Transcribe.
    interview_live_model: str = Field(
        default="muse-wonder-1.0",
        validation_alias=AliasChoices("MUSE_LIVE_MODEL", "INTERVIEW_LIVE_MODEL"),
    )
    # Empty = same as interview_live_model.
    chitti_live_model: str = ""
    # Studio voice id for the assistant's spoken reply (pipeline/tts.py).
    muse_live_voice: str = Field(
        default="Aoede",
        validation_alias=AliasChoices("MUSE_LIVE_VOICE"),
    )
    # Local hashed embeddings. Model API has no embedding endpoint.
    muse_embedding_model: str = "local-hash"
    muse_embedding_dims: int = 768
    # Thumbnails only. https://dev.meta.ai/docs/image-generation
    muse_image_model: str = Field(
        default="muse-image-1.0",
        validation_alias=AliasChoices("MUSE_IMAGE_MODEL"),
    )

    # --- Resilience & concurrency ---
    # Transient failures (rate limits, timeouts, empty JSON) are retried with
    # exponential backoff instead of breaking the run.
    llm_max_retries: int = 4
    llm_retry_base_delay: float = 1.5
    llm_timeout_seconds: float = 600.0
    # Max Muse calls to run at once. 0 = 2, so a slide build is less likely to hit a rate limit.
    llm_max_parallel: int = 2
    # VLM page extraction: small page-groups so one call is not handed a huge
    # multi-image prompt. Groups run in parallel up to llm_max_parallel.
    vlm_pages_per_call: int = 2

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _provider_is_muse(cls, v: Any) -> str:
        # Muse is the only text, vision, and image provider. Older saved values map here.
        return "muse"

    @property
    def active_provider(self) -> str:
        """Text, vision, and images go through Muse."""
        return "muse"

    @property
    def llm_text_model(self) -> str:
        return self.muse_model

    @property
    def llm_vision_model(self) -> str:
        return self.muse_vision_model

    def effective_llm_parallel(self) -> int:
        """How many Muse calls may run at once."""
        n = int(self.llm_max_parallel or 0)
        return n if n > 0 else 2

    # --- No accounts ---
    # There is no login screen. Every request runs as one local identity
    # (see app/main.py LOCAL_USER), so the app opens straight into Studio.

    # --- Cost tracking (admin only) ---
    # Estimated $ cost of LLM/paid-API usage is derived from per-model rates.
    # Provide overrides as a comma-separated list of
    #   model=INPUT_RATE/OUTPUT_RATE   (USD per 1M tokens),
    # e.g. "muse-2.5-flash=0.30/2.50,gpt-4o-mini=0.15/0.60". Unknown models
    # fall back to built-in defaults, then to $0 (treated as free/local).
    cost_rates: str = ""

    # --- Voice library limits (saved cloned voices per account) ---
    voice_limit_user: int = 10
    voice_limit_admin: int = 30

    def cost_rate_map(self) -> dict[str, tuple[float, float]]:
        """Parse ``cost_rates`` into {model: (in_rate, out_rate)}."""
        out: dict[str, tuple[float, float]] = {}
        for part in (self.cost_rates or "").split(","):
            part = part.strip()
            if not part or "=" not in part:
                continue
            model, _, rates = part.partition("=")
            try:
                in_s, _, out_s = rates.partition("/")
                out[model.strip().lower()] = (float(in_s), float(out_s or in_s))
            except (TypeError, ValueError):
                continue
        return out

    youtube_client_secrets: str = "client_secrets.json"
    youtube_privacy: str = "unlisted"
    # Public https origin of this app (no trailing slash). Required for Instagram
    # Graph API to fetch staged carousel/video URLs under /files/{job}/….
    public_base_url: str = ""

    # --- Publish metadata + thumbnail generation ---
    # Auto-generate a YouTube title/description/tags (via the active LLM) and a
    # thumbnail image before upload. Both are best-effort: if they fail the flow
    # continues with a sensible fallback and a message is surfaced.
    generate_thumbnail: bool = True
    # Optional Pillow title overlay (unused for Nano Banana which renders text).
    thumbnail_text_overlay: bool = True
    # Thumbnail image backend:
    #   "nano_banana" / "muse" / "auto" -> Muse Image (cloud).
    #   Thumbnail-only — never used for slide/content gen.
    #   "off" / "none" -> skip AI thumbnail (slide-frame fallback may still apply).
    # Local diffusion (Boogu etc.) removed for now — re-add later as optional.
    thumbnail_backend: str = "auto"
    # Experimental: AI images inside slides (UI default off until validated).
    slide_ai_images_default: bool = False

    # PDF page -> image rendering resolution for VLM extraction.
    vlm_dpi: int = 150
    vlm_max_pages: int = 15

    capture_duration: int = 20
    capture_fps: int = 24

    # Output video quality tier: "1080p" (1920x1080), "2k"/"1440p" (2560x1440),
    # or "4k" (3840x2160). Vertical formats scale to the matching short edge.
    # Slides are laid out at a logical 1080-line canvas and captured at a higher
    # device pixel ratio so text/vectors stay razor-sharp when scaled up.
    video_quality: str = "2k"
    # x264 constant-rate-factor (lower = better quality/larger file; 18-23 sane).
    video_crf: int = 16
    # Encode speed. "slow" looks marginally better but makes long (8‑min) merges
    # crawl across dozens of slide segments — use medium as the studio default.
    video_preset: str = "medium"

    # Animation mode for slide capture:
    #   "animated" -> deterministic frame-by-frame seek capture (real in-slide
    #                 motion driven by the page's frame timeline; slower render).
    #   "still"    -> one screenshot per slide (fastest; motion only via
    #                 crossfades between slides).
    animation_mode: str = "animated"
    # Seconds of entrance motion captured frame-by-frame per slide. After this
    # window the slide is static, so we capture ONE settled frame and let ffmpeg
    # hold it for the rest of the narration — this keeps real motion while
    # cutting the screenshot count from thousands to a few dozen per slide.
    motion_seconds: float = 2.0
    # Frames per second used for the seek-captured motion window. Lower than the
    # final video fps because entrance + highlight transitions read fine at a
    # modest rate, and every extra fps multiplies the screenshot count. The final
    # video is still encoded at capture_fps; ffmpeg upsamples the held frames.
    motion_fps: int = 12
    # When True the item highlight (active bullet/step/stat) walks through the
    # slide IN TIME with the narration: the whole slide duration is seek-captured
    # at motion_fps so on-screen focus stays synced to what's being explained.
    # When False only the short entrance window is captured (faster, no walk).
    sync_highlight: bool = True
    # Max PNG screenshots per slide during animated capture. When the narration-
    # synced timeline would exceed this, only entrance + highlight-transition
    # keyframes are captured (timing is preserved via keyframes.json).
    max_motion_frames: int = 72
    # How many Playwright worker processes capture slides in parallel. Slides are
    # split into this many disjoint batches, each rendered in its own browser,
    # then the segments are assembled. 0 = auto (based on CPU count).
    capture_workers: int = 0

    # Narration voice id (Kore, Aoede, Charon, …). Speech is a neural studio
    # voice; Model API does not synthesize audio.
    muse_tts_model: str = "narration"
    muse_tts_voice: str = Field(
        default="Kore",
        validation_alias=AliasChoices("MUSE_TTS_VOICE"),
    )

    @property
    def youtube_secrets_path(self) -> Path:
        p = Path(self.youtube_client_secrets)
        return p if p.is_absolute() else BASE_DIR / p

    # ===================================================== paper automation ====
    # Built-in "paper -> video" automation. Runs in-process (reuses the same
    # pipeline the UI uses) so it never needs to call the app over HTTP. The
    # admin controls it from the dashboard; it can also run on a schedule.
    # Master switch for the background scheduler (manual trigger always works).
    auto_enabled: bool = False
    # Paper source:
    #   "trending" / "auto" -> HF Daily Papers + arXiv GenAI + Semantic Scholar
    #   "hf"                -> Hugging Face Daily Papers only
    #   "arxiv"             -> arXiv Atom API
    #   "semantic_scholar"  -> Semantic Scholar bulk search
    auto_source: str = "trending"
    auto_arxiv_categories: str = "cs.LG,cs.CL,cs.CV,cs.AI,cs.NE,stat.ML"
    # Extra arXiv abs/ti keyword clause (GenAI-focused). Empty = built-in defaults.
    auto_arxiv_keywords: str = ""
    auto_ss_query: str = (
        "large language model OR multimodal OR diffusion OR generative AI "
        "OR vision language OR agentic OR RLHF"
    )
    auto_ss_api_key: str = ""
    # Only keep papers that reference a code repo (keeps the "with code" spirit).
    # When none match, the engine falls back to newest PDF with a log note.
    auto_require_code: bool = True
    # How many papers to process per run (preview UI shows the same queue, up to 3).
    auto_max_papers: int = 3
    # Outputs per paper.
    auto_make_video: bool = True
    auto_video_format: str = "youtube_video"
    auto_video_seconds: int = 480  # 8 min default for cron papers
    # Reels/Instagram are a manual Studio format choice — cron/automation renders
    # long-form video only so one paper does not spawn two History jobs.
    auto_make_reel: bool = False
    auto_reel_format: str = "instagram_reels"
    auto_reel_seconds: int = 45
    auto_video_theme: str = "snow"
    auto_video_style: str = "whiteboard"  # Teach · board
    # Studio voice for cron narration (Kore, Charon, Aoede, …).
    auto_muse_voice: str = "Kore"
    # Generate a thumbnail into the paper output folder after each render.
    auto_generate_thumbnail: bool = True
    # Push to YouTube after render (only if client_secrets.json is present).
    auto_publish: bool = False
    # Root folder for per-paper output folders.
    auto_output_dir: str = "automation_output"
    # --- schedule: run twice a day in non-working hours ---
    # Comma-separated hours-of-day (0-23). Default 01:00 & 19:00 stay outside
    # the 9–18 working-hours block (13:00 was previously blocked by that window).
    auto_run_hours: str = "1,19"
    # Working-hours window to AVOID auto-runs in (inclusive start, exclusive end).
    auto_work_start_hour: int = 9
    auto_work_end_hour: int = 18
    # --- compute gating (only run when the machine is free) ---
    auto_compute_gate: bool = True
    auto_max_load: float = 0.85
    auto_min_gpu_free_mb: int = 0
    auto_compute_wait_seconds: int = 1800

    # --- compute gating (only run when the machine is free) ---
    # When the user lists extra topics, we scrape/search the public web and
    # inject fresh facts/examples into slide generation. Free backends
    # (DuckDuckGo via ``ddgs``, Wikipedia, Jina Reader) always run; optional
    # API keys below are raced first for speed/quality when present.
    topic_research_enabled: bool = True
    topic_research_max_results: int = 4
    topic_research_fetch_pages: int = 2
    topic_research_timeout: float = 8.0
    brave_api_key: str = ""
    tavily_api_key: str = ""
    serper_api_key: str = ""

    @property
    def auto_output_path(self) -> Path:
        p = Path(self.auto_output_dir)
        return p if p.is_absolute() else BASE_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
