"""Fetch latest / trending GenAI papers from live sources.

Sources (configurable via ``AUTO_SOURCE``):

* ``trending`` / ``auto`` (default): merge Hugging Face Daily Papers (trending)
  + arXiv GenAI keyword query + Semantic Scholar bulk (newest OA PDFs).
* ``hf`` / ``huggingface``: Hugging Face Daily Papers only.
* ``arxiv``: arXiv Atom API (categories ± GenAI keyword filter).
* ``semantic_scholar``: Semantic Scholar Graph bulk search (publicationDate sort).

Only the Python standard library is used (no new dependencies).
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree as ET

_LOG = logging.getLogger("app.automation.sources")
_S2_COOLDOWN_UNTIL = 0.0

_UA = {"User-Agent": "multimodal-studio-automation/2.1 (+https://localhost)"}
_CODE_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|hf\.co|huggingface\.co)"
    r"/[\w.\-/%]+",
    re.I,
)
# Soft GenAI relevance signals (title/abstract). Used to rank / filter.
_GENAI_RE = re.compile(
    r"\b("
    r"large language model|language model|\bllms?\b|foundation model|"
    r"generative ai|genai|gpt-\d|chatgpt|muse|claude|"
    r"diffusion|stable diffusion|text-to-image|text-to-video|"
    r"multimodal|vision[- ]language|\bvlm\b|\bmllm\b|"
    r"transformer|attention mechanism|in[- ]context learning|"
    r"retrieval[- ]augmented|\brag\b|agentic|\bagents?\b|"
    r"reinforcement learning from human feedback|\brlhf\b|"
    r"instruction tun|chain[- ]of[- ]thought|\bcot\b|"
    r"reasoning model|test[- ]time compute|mixture of experts|\bmoe\b|"
    r"fine[- ]tun|lora|qlora|peft|prompt engineer|"
    r"open[- ]weight|open[- ]source model|benchmark"
    r")\b",
    re.I,
)

# Default arXiv abs/ti keyword clause for GenAI when no custom query is set.
_DEFAULT_ARXIV_KEYWORDS = (
    'abs:"large language" OR abs:LLM OR abs:multimodal OR abs:diffusion '
    'OR abs:"generative" OR abs:VLM OR abs:agentic OR abs:RLHF '
    'OR ti:"language model" OR ti:multimodal OR ti:diffusion'
)


def _clean_code_url(url: str) -> str:
    """Trim trailing punctuation the abstract text often glues onto a URL."""
    return url.rstrip(".,;:)]}\"'") if url else ""


@dataclass
class Paper:
    id: str  # stable id used for dedup (e.g. arxiv id or S2 paperId)
    title: str
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    pdf_url: str = ""
    code_url: str = ""
    published: str = ""
    source: str = ""
    score: float = 0.0  # trending / ranking hint (higher = better)
    url: str = ""  # landing page (abs / HF / S2)

    @property
    def has_code(self) -> bool:
        return bool(self.code_url)

    @property
    def is_genai(self) -> bool:
        blob = f"{self.title}\n{self.abstract}"
        return bool(_GENAI_RE.search(blob))


def _get(url: str, headers: dict | None = None, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={**_UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _find_code(*texts: str) -> str:
    for t in texts:
        if not t:
            continue
        m = _CODE_RE.search(t)
        if m:
            return _clean_code_url(m.group(0))
    return ""


def _genai_boost(paper: Paper) -> float:
    boost = 0.0
    if paper.is_genai:
        boost += 5.0
    if paper.has_code:
        boost += 2.0
    if paper.pdf_url:
        boost += 1.0
    # Prefer very recent dates.
    if paper.published:
        try:
            d = paper.published[:10]
            age = (date.today() - date.fromisoformat(d)).days
            if age <= 2:
                boost += 3.0
            elif age <= 7:
                boost += 1.5
        except ValueError:
            pass
    return paper.score + boost


# --------------------------------------------------------------------- arXiv --

_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}


def _fetch_arxiv(
    categories: list[str],
    limit: int,
    *,
    keywords: str = "",
) -> list[Paper]:
    """Fetch recent arXiv papers, optionally AND-filtered by GenAI keywords."""
    cats = [c.strip() for c in categories if c and c.strip()] or ["cs.LG", "cs.CL", "cs.AI"]
    cat_q = "+OR+".join(f"cat:{c}" for c in cats)
    kw = (keywords or "").strip() or _DEFAULT_ARXIV_KEYWORDS
    # Encode keyword clause for the arXiv query language (spaces → +).
    kw_enc = urllib.parse.quote_plus(kw).replace("%28", "(").replace("%29", ")").replace(
        "%22", "%22"
    )
    # arXiv wants +OR+ style; quote_plus already turns spaces into +.
    search = f"({cat_q})+AND+({kw_enc})"
    fetch_n = max(limit * 10, 40)
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query={search}&sortBy=submittedDate&sortOrder=descending"
        f"&start=0&max_results={fetch_n}"
    )
    try:
        raw = _get(url)
    except Exception as e:
        _LOG.warning("arxiv keyword query failed (%s); falling back to categories only", e)
        return _fetch_arxiv_categories_only(cats, limit)

    papers = _parse_arxiv_atom(raw, source="arxiv")
    if not papers:
        _LOG.warning("arxiv keyword query returned 0; falling back to categories only")
        return _fetch_arxiv_categories_only(cats, limit)
    return papers


def _fetch_arxiv_categories_only(categories: list[str], limit: int) -> list[Paper]:
    cat_q = "+OR+".join(f"cat:{c}" for c in categories) or "cat:cs.LG"
    fetch_n = max(limit * 10, 40)
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query={cat_q}&sortBy=submittedDate&sortOrder=descending"
        f"&start=0&max_results={fetch_n}"
    )
    raw = _get(url)
    return _parse_arxiv_atom(raw, source="arxiv")


def _parse_arxiv_atom(raw: bytes, *, source: str) -> list[Paper]:
    root = ET.fromstring(raw)
    papers: list[Paper] = []
    for e in root.findall("a:entry", _ARXIV_NS):
        eid = (e.findtext("a:id", "", _ARXIV_NS) or "").strip()
        # normalize https://arxiv.org/abs/2401.01234v2 -> 2401.01234
        m = re.search(r"arxiv\.org/abs/([^?#\s]+)", eid)
        arxiv_id = m.group(1) if m else eid.rsplit("/", 1)[-1]
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        title = " ".join((e.findtext("a:title", "", _ARXIV_NS) or "").split())
        summary = " ".join((e.findtext("a:summary", "", _ARXIV_NS) or "").split())
        comment = e.findtext("{http://arxiv.org/schemas/atom}comment", "") or ""
        authors = [
            (a.findtext("a:name", "", _ARXIV_NS) or "").strip()
            for a in e.findall("a:author", _ARXIV_NS)
        ]
        pdf_url = ""
        abs_url = ""
        for link in e.findall("a:link", _ARXIV_NS):
            rel = link.get("rel") or ""
            href = link.get("href") or ""
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = href
            if rel == "alternate" and href:
                abs_url = href
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        if not abs_url and arxiv_id:
            abs_url = f"https://arxiv.org/abs/{arxiv_id}"
        code = _find_code(summary, comment)
        papers.append(
            Paper(
                id=f"arxiv:{arxiv_id}",
                title=title or arxiv_id,
                abstract=summary,
                authors=[a for a in authors if a],
                pdf_url=pdf_url,
                code_url=code,
                published=(e.findtext("a:published", "", _ARXIV_NS) or "").strip(),
                source=source,
                url=abs_url,
            )
        )
    return papers


# --------------------------------------------------------- Semantic Scholar --


def _fetch_semantic_scholar(query: str, limit: int, api_key: str = "") -> list[Paper]:
    """Newest papers via the bulk search endpoint (supports ``sort``).

    Prefers open-access PDFs; falls back to arXiv PDF URLs from ``externalIds``.
    Soft-fails on HTTP 429 (unauthenticated S2 is aggressively rate-limited).
    """
    global _S2_COOLDOWN_UNTIL
    if time.time() < _S2_COOLDOWN_UNTIL:
        return []

    fields = "title,abstract,authors,openAccessPdf,externalIds,publicationDate,url"
    fetch_n = max(limit * 12, 50)
    q = (query or "").strip() or (
        "large language model OR multimodal OR diffusion OR generative AI OR VLM"
    )
    headers = {"x-api-key": api_key} if api_key else {}
    papers: list[Paper] = []
    token = ""
    pages = 0
    was_rate_limited = False
    while len(papers) < fetch_n and pages < 3:
        params = {"query": q, "fields": fields, "sort": "publicationDate:desc"}
        if token:
            params["token"] = token
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/search/bulk?"
            + urllib.parse.urlencode(params)
        )
        try:
            data = json.loads(_get(url, headers=headers).decode("utf-8", "replace"))
        except Exception as e:
            err = str(e)
            if "429" in err:
                _S2_COOLDOWN_UNTIL = time.time() + 300.0  # 5m cooloff
                _LOG.warning("S2 rate-limited (429); pausing Semantic Scholar calls for 5m")
                was_rate_limited = True
                break
            _LOG.warning("S2 bulk failed (%s); trying relevance search", e)
            return papers or _fetch_semantic_scholar_relevance(q, limit, api_key)
        pages += 1
        for it in data.get("data") or []:
            paper = _paper_from_s2(it)
            if paper and paper.pdf_url:
                papers.append(paper)
            if len(papers) >= fetch_n:
                break
        token = (data.get("token") or "").strip()
        if not token:
            break
    if not papers and not was_rate_limited:
        return _fetch_semantic_scholar_relevance(q, limit, api_key)
    return papers


def _fetch_semantic_scholar_relevance(query: str, limit: int, api_key: str = "") -> list[Paper]:
    """Fallback: regular search (relevance). Filter to items with OA PDF."""
    global _S2_COOLDOWN_UNTIL
    if time.time() < _S2_COOLDOWN_UNTIL:
        return []

    fields = "title,abstract,authors,openAccessPdf,externalIds,publicationDate,url"
    fetch_n = max(limit * 12, 50)
    year = date.today().year
    params = urllib.parse.urlencode(
        {
            "query": query,
            "fields": fields,
            "limit": min(fetch_n, 100),
            "year": f"{year - 1}-{year}",
            "openAccessPdf": "",
        }
    )
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"
    headers = {"x-api-key": api_key} if api_key else {}
    try:
        data = json.loads(_get(url, headers=headers).decode("utf-8", "replace"))
    except Exception as e:
        err = str(e)
        if "429" in err:
            _S2_COOLDOWN_UNTIL = time.time() + 300.0  # 5m cooloff
            _LOG.warning("S2 rate-limited (429); pausing Semantic Scholar calls for 5m")
        else:
            _LOG.warning("S2 relevance search failed: %s", e)
        return []
    papers: list[Paper] = []
    for it in data.get("data") or []:
        paper = _paper_from_s2(it)
        if paper and paper.pdf_url:
            papers.append(paper)
    return papers


def _paper_from_s2(it: dict) -> Paper | None:
    if not it:
        return None
    oa = it.get("openAccessPdf") or {}
    pdf_url = (oa.get("url") or "").strip()
    ext = it.get("externalIds") or {}
    arxiv_raw = (ext.get("ArXiv") or "").strip()
    arxiv_id = re.sub(r"v\d+$", "", arxiv_raw) if arxiv_raw else ""
    if not pdf_url and arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    abstract = it.get("abstract") or ""
    code = _find_code(abstract)
    # Prefer arXiv id for stable dedup across sources.
    if arxiv_id:
        pid = f"arxiv:{arxiv_id}"
        source = "semantic_scholar+arxiv"
        url = f"https://arxiv.org/abs/{arxiv_id}"
    else:
        pid = f"s2:{it.get('paperId')}"
        source = "semantic_scholar"
        url = (it.get("url") or "").strip()
    title = (it.get("title") or "").strip()
    if not title:
        return None
    return Paper(
        id=pid,
        title=title,
        abstract=abstract,
        authors=[a.get("name", "") for a in (it.get("authors") or []) if a.get("name")],
        pdf_url=pdf_url,
        code_url=code,
        published=str(it.get("publicationDate") or ""),
        source=source,
        url=url,
    )


# ----------------------------------------------------- Hugging Face Daily -----


def _fetch_hf_daily(limit: int, *, days_back: int = 3) -> list[Paper]:
    """Hugging Face Daily Papers — community-curated / trending GenAI feed."""
    papers: list[Paper] = []
    seen: set[str] = set()
    # Try "today" without date (current feed), then walk back a few days.
    urls = ["https://huggingface.co/api/daily_papers?limit=50"]
    today = date.today()
    for d in range(0, max(1, days_back)):
        day = today - timedelta(days=d)
        urls.append(
            f"https://huggingface.co/api/daily_papers?date={day.isoformat()}"
            f"&limit=50&sort=trending"
        )
        urls.append(
            f"https://huggingface.co/api/daily_papers?date={day.isoformat()}&limit=50"
        )

    for url in urls:
        if len(papers) >= max(limit * 8, 25):
            break
        try:
            data = json.loads(_get(url, timeout=30).decode("utf-8", "replace"))
        except Exception as e:
            _LOG.debug("HF daily_papers failed for %s: %s", url, e)
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            p = _paper_from_hf(item)
            if not p or p.id in seen:
                continue
            seen.add(p.id)
            papers.append(p)
    return papers


def _paper_from_hf(item: dict) -> Paper | None:
    if not isinstance(item, dict):
        return None
    meta = item.get("paper") if isinstance(item.get("paper"), dict) else item
    arxiv_id = str(meta.get("id") or "").strip()
    if not arxiv_id:
        return None
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
    title = (item.get("title") or meta.get("title") or "").strip()
    abstract = (item.get("summary") or meta.get("summary") or meta.get("abstract") or "")
    abstract = " ".join(str(abstract).split())
    authors = []
    for a in meta.get("authors") or []:
        if isinstance(a, dict):
            name = (a.get("name") or "").strip()
            if name:
                authors.append(name)
        elif isinstance(a, str) and a.strip():
            authors.append(a.strip())
    upvotes = 0
    try:
        upvotes = int(meta.get("upvotes") or item.get("upvotes") or 0)
    except (TypeError, ValueError):
        upvotes = 0
    published = (
        meta.get("publishedAt")
        or item.get("publishedAt")
        or meta.get("submittedOnDailyAt")
        or ""
    )
    if isinstance(published, str) and "T" in published:
        published = published[:10]
    code = _find_code(abstract)
    return Paper(
        id=f"arxiv:{arxiv_id}",
        title=title or arxiv_id,
        abstract=abstract,
        authors=authors,
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        code_url=code,
        published=str(published)[:32],
        source="huggingface",
        score=float(upvotes),
        url=f"https://huggingface.co/papers/{arxiv_id}",
    )


# --------------------------------------------------------------- public API --


def _dedupe_rank(papers: list[Paper], limit: int) -> list[Paper]:
    """Dedupe by id, rank by GenAI/trending score, return top candidates."""
    best: dict[str, Paper] = {}
    for p in papers:
        if not p.id or not p.title:
            continue
        prev = best.get(p.id)
        if prev is None or _genai_boost(p) > _genai_boost(prev):
            # Merge code_url / pdf if missing on the winner.
            if prev is not None:
                if not p.code_url and prev.code_url:
                    p.code_url = prev.code_url
                if not p.pdf_url and prev.pdf_url:
                    p.pdf_url = prev.pdf_url
                if not p.abstract and prev.abstract:
                    p.abstract = prev.abstract
                p.score = max(p.score, prev.score)
            best[p.id] = p
    ranked = sorted(best.values(), key=_genai_boost, reverse=True)
    # Prefer GenAI-looking papers first, but never return empty if we have PDFs.
    genai = [p for p in ranked if p.is_genai and p.pdf_url]
    rest = [p for p in ranked if p not in genai and p.pdf_url]
    ordered = genai + rest
    return ordered[: max(limit * 10, 40)]


import time

_FETCH_CACHE: dict[tuple, tuple[float, list[Paper]]] = {}
_FETCH_CACHE_TTL = 900  # 15 minutes

def fetch_latest(config) -> list[Paper]:
    """Return recent/trending papers newest / hottest first.

    Filtering (require_code) and final ``max_papers`` trim are applied by the
    caller; this returns a generous, ordered candidate list.
    """
    src = (getattr(config, "source", None) or "trending").strip().lower()
    limit = int(getattr(config, "max_papers", 1) or 1)
    cats = list(getattr(config, "arxiv_categories", None) or [])
    keywords = str(getattr(config, "arxiv_keywords", "") or "")
    ss_query = str(getattr(config, "ss_query", "") or "")
    ss_key = str(getattr(config, "ss_api_key", "") or "")

    cache_key = (src, limit, tuple(cats), keywords, ss_query)
    now = time.time()
    if cache_key in _FETCH_CACHE:
        ts, cached_papers = _FETCH_CACHE[cache_key]
        if now - ts < _FETCH_CACHE_TTL:
            _LOG.info(f"returning {len(cached_papers)} candidate papers from cache")
            return cached_papers

    collected: list[Paper] = []
    errors: list[str] = []

    def _safe(name: str, fn) -> None:
        try:
            got = fn() or []
            collected.extend(got)
            _LOG.info("%s: %d paper(s)", name, len(got))
        except Exception as e:
            msg = f"{name}: {e}"
            errors.append(msg)
            _LOG.warning("source failed — %s", msg)

    if src in {"trending", "auto", "all", "genai"}:
        _safe("huggingface", lambda: _fetch_hf_daily(limit))
        _safe("arxiv", lambda: _fetch_arxiv(cats, limit, keywords=keywords))
        _safe("semantic_scholar", lambda: _fetch_semantic_scholar(ss_query, limit, ss_key))
    elif src in {"hf", "huggingface", "daily_papers"}:
        _safe("huggingface", lambda: _fetch_hf_daily(limit))
    elif src in {"semantic_scholar", "s2", "semanticscholar"}:
        _safe("semantic_scholar", lambda: _fetch_semantic_scholar(ss_query, limit, ss_key))
    else:
        # arxiv (default legacy name still works)
        _safe("arxiv", lambda: _fetch_arxiv(cats, limit, keywords=keywords))

    if not collected and errors:
        # Last-ditch: plain arXiv categories so automation never goes fully dry.
        _safe("arxiv_fallback", lambda: _fetch_arxiv_categories_only(cats or ["cs.LG", "cs.CL", "cs.AI"], limit))

    out = _dedupe_rank(collected, limit)
    _FETCH_CACHE[cache_key] = (now, out)
    return out


def slugify(title: str, paper_id: str) -> str:
    """Filesystem-safe folder name: ``YYYYMMDD_title-slug_shortid``."""
    base = re.sub(r"[^\w\s-]", "", (title or "paper").lower()).strip()
    base = re.sub(r"[\s_-]+", "-", base)[:70].strip("-") or "paper"
    short = re.sub(r"[^\w.]", "", paper_id.split(":")[-1])[:16]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{stamp}_{base}_{short}" if short else f"{stamp}_{base}"


def pdf_basename(title: str, paper_id: str = "") -> str:
    """Human PDF filename from paper title (never a bare ``paper.pdf``)."""
    base = re.sub(r"[^\w\s-]", "", (title or "paper").lower()).strip()
    base = re.sub(r"[\s_-]+", "-", base)[:80].strip("-") or "paper"
    short = re.sub(r"[^\w.]", "", (paper_id or "").split(":")[-1])[:12]
    stem = f"{base}_{short}" if short else base
    return f"{stem}.pdf"


def resolve_pdf_path(folder, meta: dict | None = None):
    """Locate the source PDF in a paper folder (named file or legacy paper.pdf)."""
    from pathlib import Path

    root = Path(folder)
    meta = meta or {}
    candidates: list = []
    named = str(meta.get("pdf_file") or "").strip()
    if named and not named.startswith(".") and "/" not in named and "\\" not in named:
        candidates.append(root / named)
    title = str(meta.get("title") or "").strip()
    pid = str(meta.get("id") or "").strip()
    if title or pid:
        candidates.append(root / pdf_basename(title, pid))
    candidates.append(root / "paper.pdf")
    # Any other single PDF at the folder root (prefer largest / newest named).
    extras = sorted(
        (p for p in root.glob("*.pdf") if p.is_file()),
        key=lambda p: (p.name == "paper.pdf", -p.stat().st_size if p.exists() else 0),
    )
    for p in candidates + extras:
        if p.is_file() and p.stat().st_size >= 1024:
            return p
    return root / (named or pdf_basename(title or root.name, pid) if (title or pid) else "paper.pdf")


def find_or_create_folder(output_dir, paper: Paper):
    """Reuse an existing folder for the same paper id (stable across retries)."""
    from pathlib import Path

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    for d in root.iterdir():
        if not d.is_dir():
            continue
        pj = d / "paper.json"
        if not pj.is_file():
            continue
        try:
            meta = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("id") == paper.id:
            return d
    return root / slugify(paper.title, paper.id)
