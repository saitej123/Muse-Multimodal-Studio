"""Multi-format content extraction with vision-first analysis.

Pipeline:

* **PDF / images** -> rendered to page PNGs and analysed by Muse Wonder. This
  reads diagrams, charts, screenshots and scanned text far more faithfully than
  plain text extraction. Standalone image uploads use a dedicated image-
  understanding prompt (content + Figure: blocks; never picks video style/theme).
* **Office / text documents** (docx, pptx, txt, md, html, rtf, csv, ...) ->
  text is extracted directly; any embedded images are pulled out and ALSO sent
  to the VLM so pictures in the document are described, not lost.

Everything degrades gracefully: if no VLM is available, or a converter is
missing, we fall back to the best plain-text path we can.
"""
from __future__ import annotations

from pathlib import Path

from ..config import get_settings
from ..logging_setup import log
from . import muse_client

# Shared boundary: image *understanding* extracts meaning — never Studio look.
_VLM_LOOK_BOUNDARY = """
STRICT BOUNDARIES (do not violate):
- Extract MEANING and CONTENT only (ideas, data, labels, relationships, steps).
- Do NOT invent or recommend a presentation visual style, color theme, brand
  palette, font, or narration voice.
- Do NOT "match" the page's colors, wallpaper, or deck chrome into a video look.
  Studio defaults already control how the finished video will look.
- Do NOT invent content that is not present.
- Do NOT be a dumb OCR dump: skip decorative noise; prioritize what a learner
  needs to understand.
""".strip()

# Vision prompt: PDF / rendered page images — understand + teach, not OCR spam.
VLM_EXTRACT_PROMPT = f"""You are an expert document analyst and teacher with strong
image understanding. Analyse the page image(s) and produce clean, teachable markdown.

Do ALL of the following:
- Transcribe every meaningful heading, paragraph, bullet, definition, formula
  and caption, preserving logical reading order (markdown headings + lists).
- For EVERY diagram, chart, screenshot, table or figure: UNDERSTAND it — what
  system/idea it shows, how parts relate, what changes left→right or top→bottom —
  then write that under a line starting with "Figure:". Include key labels, data
  trends, arrows/flows, and the teaching takeaway. Do not say "an image of…".
- If there is a process or workflow, summarise it as ordered steps.
- Prefer mechanisms and relationships over vague aesthetics.

{_VLM_LOOK_BOUNDARY}

Return only the structured markdown.
"""

# Standalone uploaded images — smart image understanding (diagrams, boards, UIs).
VLM_STANDALONE_IMAGE_PROMPT = f"""You are an expert teacher with excellent image
understanding. The input is an uploaded image (diagram, chart, screenshot,
whiteboard photo, slide capture, or photo of notes) — NOT a random photo to
caption shallowly.

Your job is IMAGE UNDERSTANDING for teaching:
1. Read and transcribe all meaningful text (headings, bullets, formulas,
   UI labels, axis titles) in reading order.
2. For the visual structure, write one or more "Figure:" blocks that explain:
   - the concept / system being shown
   - nodes, arrows, layers, axes, and how they connect
   - the learner takeaway (what to remember)
3. If it is a process or architecture, also list ordered steps.
4. Be specific and concrete. Never: "this image shows a colorful diagram"
   or "various boxes and arrows". Name the parts and relationships you see.
5. If text is blurry, say what you can confidently read; do not invent.

{_VLM_LOOK_BOUNDARY}
Ignore decorative colors, shadows, watermarks, and brand chrome.

Return only the structured markdown.
"""

# Embedded images inside docx/pptx (when LibreOffice PDF conversion is unavailable).
VLM_IMAGE_PROMPT = f"""These images were embedded inside a document.
Use image understanding — not shallow captions.

For EACH image, write a teachable "Figure:" block covering:
- the concept or system depicted (not "a picture of…")
- key labels, data, axes, nodes, arrows, or steps visible
- how parts relate and why it matters for the surrounding document

Be concrete; do not invent details that are not visible.

{_VLM_LOOK_BOUNDARY}

Return only markdown.
"""

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
PDF_LIKE = {".pdf"}


# ------------------------------------------------------------------ rendering ----

def render_pdf_to_images(
    pdf_path: Path, out_dir: Path, *, max_pages: int | None = None
) -> list[Path]:
    """Render PDF pages to PNG images using PyMuPDF (no external deps)."""
    import fitz  # PyMuPDF

    settings = get_settings()
    out_dir.mkdir(parents=True, exist_ok=True)
    zoom = settings.vlm_dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    limit = int(max_pages) if max_pages is not None else int(settings.vlm_max_pages)

    paths: list[Path] = []
    doc = fitz.open(str(pdf_path))
    try:
        for i, page in enumerate(doc):
            if i >= limit:
                break
            pix = page.get_pixmap(matrix=matrix)
            img_path = out_dir / f"page_{i:03d}.png"
            pix.save(str(img_path))
            paths.append(img_path)
    finally:
        doc.close()
    return paths


def _copy_image_input(src: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"page_000{src.suffix.lower()}"
    dest.write_bytes(src.read_bytes())
    return [dest]


# ------------------------------------------------------- office/text -> pdf ----

def _office_to_pdf(src: Path, out_dir: Path) -> Path | None:
    """Convert an office/text document to PDF via LibreOffice, if available.

    A PDF lets us use the high-quality vision path (pictures + layout). Returns
    the produced PDF path, or None when LibreOffice isn't installed.
    """
    import shutil
    import subprocess

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir",
             str(out_dir), str(src)],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except Exception as e:
        log.bind(task="extract").warning(f"LibreOffice convert failed: {e}")
        return None
    pdf = out_dir / (src.stem + ".pdf")
    return pdf if pdf.exists() else None


# ---------------------------------------------------- text-only extractors ----

def _text_from_docx(path: Path) -> str:
    from docx import Document  # python-docx

    doc = Document(str(path))
    lines = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines).strip()


def _text_from_pptx(path: Path) -> str:
    from pptx import Presentation  # python-pptx

    prs = Presentation(str(path))
    lines: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        lines.append(f"\n## Slide {i}")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                lines.append(shape.text_frame.text.strip())
    return "\n".join(lines).strip()


def _text_from_html(path: Path) -> str:
    import re

    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    import html as _html

    text = _html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", text)).strip()


def _text_from_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def _embedded_images(path: Path, out_dir: Path) -> list[Path]:
    """Pull images out of a docx/pptx (both are zip archives) for VLM analysis."""
    import zipfile

    out: list[Path] = []
    try:
        with zipfile.ZipFile(str(path)) as z:
            names = [
                n for n in z.namelist()
                if "media/" in n.lower()
                and Path(n).suffix.lower() in IMAGE_SUFFIXES
            ]
            out_dir.mkdir(parents=True, exist_ok=True)
            settings = get_settings()
            for i, n in enumerate(names[: settings.vlm_max_pages]):
                data = z.read(n)
                dest = out_dir / f"img_{i:03d}{Path(n).suffix.lower()}"
                dest.write_bytes(data)
                out.append(dest)
    except Exception:
        return []
    return out


def extract_text_any(path: Path) -> str:
    """Best-effort plain-text extraction for any supported document type."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return extract_text_only(path)
        if suffix in {".docx"}:
            return _text_from_docx(path)
        if suffix in {".pptx"}:
            return _text_from_pptx(path)
        if suffix in {".html", ".htm"}:
            return _text_from_html(path)
        if suffix in {".txt", ".md", ".markdown", ".csv", ".rtf"}:
            return _text_from_plain(path)
    except Exception as e:
        log.bind(task="extract").warning(f"text extraction for {suffix} failed: {e}")
    # Last resort: try reading as plain text.
    try:
        return _text_from_plain(path)
    except Exception:
        return ""


# ------------------------------------------------------------------ public ----

def extract_with_vlm(
    input_path: Path,
    work_dir: Path,
    *,
    vision_model: str | None = None,
) -> tuple[str, list[Path]]:
    """Returns (markdown_text, page_image_paths). Uses the vision model.

    Strategy by type:
    * PDF / image  -> render to page images and analyse with the VLM.
    * Office/text  -> try converting to PDF for the rich vision path; otherwise
      extract text directly and additionally describe any embedded images.

    Optional ``vision_model`` overrides the default VLM (Interview Prep uses
    Muse Spark or Muse Wonder).
    """
    images_dir = work_dir / "pages"
    suffix = input_path.suffix.lower()

    base_prompt = VLM_EXTRACT_PROMPT
    if suffix in PDF_LIKE:
        images = render_pdf_to_images(input_path, images_dir)
    elif suffix in IMAGE_SUFFIXES:
        images = _copy_image_input(input_path, images_dir)
        base_prompt = VLM_STANDALONE_IMAGE_PROMPT
        log.bind(task="extract").info(
            f"standalone image → VLM image-understanding ({input_path.name})"
        )
    elif suffix in {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm"}:
        # Plain text formats don't benefit from LibreOffice PDF layout rendering.
        # Just read the text directly (no VLM needed for the text itself).
        text = extract_text_any(input_path)
        return text, []
    else:
        # Office document (docx, pptx, etc). Prefer converting to PDF so the VLM sees layout
        # + pictures; fall back to text + embedded-image description.
        pdf = _office_to_pdf(input_path, work_dir / "converted")
        if pdf is not None:
            log.bind(task="extract").info(f"converted {suffix} -> PDF for vision analysis")
            images = render_pdf_to_images(pdf, images_dir)
        else:
            text = extract_text_any(input_path)
            embedded = _embedded_images(input_path, images_dir)
            if embedded:
                log.bind(task="extract").info(
                    f"describing {len(embedded)} embedded image(s) via VLM"
                )
                try:
                    desc = _describe_images_batched(
                        embedded, vision_model=vision_model
                    )
                    if desc.strip():
                        text = f"{text}\n\n## Figures\n{desc.strip()}"
                except Exception as e:
                    log.bind(task="extract").warning(f"embedded image VLM failed: {e}")
            return text.strip(), embedded

    if not images:
        return "", []

    text = _extract_pages_batched(
        images, vision_model=vision_model, prompt=base_prompt
    )
    return text.strip(), images


def _describe_images_batched(
    images: list[Path], *, vision_model: str | None = None
) -> str:
    """Describe embedded figures in small batches (same limits as page extract)."""
    settings = get_settings()
    per = max(1, int(getattr(settings, "vlm_pages_per_call", 2)))
    if len(images) <= per:
        return muse_client.generate_from_images(
            VLM_IMAGE_PROMPT, images, model=vision_model
        )

    groups = [images[i:i + per] for i in range(0, len(images), per)]
    log.bind(task="extract").info(
        f"embedded image VLM: {len(images)} image(s) in {len(groups)} group(s)"
    )

    def _one(group: list[Path]) -> str:
        return muse_client.generate_from_images(
            VLM_IMAGE_PROMPT, group, model=vision_model
        )

    results = muse_client.parallel_map(_one, groups, ordered=True)
    parts: list[str] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception) or not (isinstance(res, str) and res.strip()):
            log.bind(task="extract").warning(
                f"embedded image group {i + 1}/{len(groups)} failed ({res}); skipping"
            )
            continue
        parts.append(res.strip())
    return "\n\n".join(parts).strip()


def _extract_pages_batched(
    images: list[Path],
    *,
    vision_model: str | None = None,
    prompt: str | None = None,
) -> str:
    """Transcribe page / standalone images in small groups, in parallel where possible.

    Handing Muse a single prompt
    with many images is slow and often truncates or OOMs. Splitting into small
    page-groups keeps each call cheap and lets cloud providers fan out. Groups
    are transcribed concurrently (clamped to 1 for Ollama) and stitched back in
    page order. If a group fails after retries it's skipped with a marker so the
    rest of the document still produces a lesson — the run never breaks.
    """
    base = (prompt or VLM_EXTRACT_PROMPT).strip()
    settings = get_settings()
    per = max(1, int(getattr(settings, "vlm_pages_per_call", 2)))
    groups = [images[i:i + per] for i in range(0, len(images), per)]
    single_call = len(groups) == 1

    def _one(group: list[Path]) -> str:
        call_prompt = base
        if not single_call:
            # Anchor each group to its page range so ordering/continuity is clear.
            start = images.index(group[0]) + 1
            end = images.index(group[-1]) + 1
            span = f"page {start}" if start == end else f"pages {start}-{end}"
            call_prompt = f"{base}\nThese image(s) are {span} of the document."
        return muse_client.generate_from_images(call_prompt, group, model=vision_model)

    if single_call:
        # Preserve the simple path (with retry already inside the client).
        try:
            return muse_client.generate_from_images(
                base, images, model=vision_model
            )
        except Exception as e:
            log.bind(task="extract").warning(f"VLM extraction failed: {e}")
            return ""

    log.bind(task="extract").info(
        f"VLM extraction: {len(images)} pages in {len(groups)} group(s) "
        f"(parallel={settings.effective_llm_parallel()})"
    )
    results = muse_client.parallel_map(_one, groups, ordered=True)
    parts: list[str] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception) or not (isinstance(res, str) and res.strip()):
            log.bind(task="extract").warning(
                f"page group {i + 1}/{len(groups)} failed ({res}); skipping"
            )
            continue
        parts.append(res.strip())
    return "\n\n".join(parts).strip()


def extract_text_only(pdf_path: Path) -> str:
    """Plain text fallback via pypdf (PDF only)."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    chunks = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(chunks).strip()
