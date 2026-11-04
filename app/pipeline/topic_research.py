"""Live web research for the Studio "Add topics" field.

When a user lists extra topics (e.g. ``real-world examples, common mistakes``),
we pull fresh snippets and short page extracts from the public web and inject
them into the slide-authoring prompt.

Search backends (tried in parallel; first good result wins, others cancel):

1. **Brave Search** — ``BRAVE_API_KEY`` (fast commercial API)
2. **Tavily** — ``TAVILY_API_KEY`` (research-oriented)
3. **Serper** — ``SERPER_API_KEY`` (web search results)
4. **DuckDuckGo** — ``ddgs`` package (free default)
5. **Wikipedia** — REST + opensearch (always-on free fallback)

Page fetch backends (for the top URLs from search):

1. **Jina Reader** (``r.jina.ai``) — markdown extract
2. **Direct HTTP** + lightweight HTML strip
"""
from __future__ import annotations

import html as html_lib
import json
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from dataclasses import dataclass, field, asdict
from typing import Any
from xml.etree import ElementTree as ET

import httpx
from loguru import logger

from ..config import get_settings

log = logger.bind(task="topic_research")

_UA = (
    "Mozilla/5.0 (compatible; MultimodalStudio/1.0; +https://localhost) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TAG_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>", re.I)
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


@dataclass
class Hit:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    score: int = 0  # optional trending signal (e.g. HN points)


@dataclass
class TopicBrief:
    topic: str
    hits: list[Hit] = field(default_factory=list)
    extracts: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    backends_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "hits": [asdict(h) for h in self.hits],
            "extracts": self.extracts,
            "notes": self.notes,
            "backends_used": self.backends_used,
        }


def parse_topics(raw: str) -> list[str]:
    """Split a comma/semicolon/newline topic string into clean unique topics."""
    parts = re.split(r"[,;\n]+", raw or "")
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        t = re.sub(r"\s+", " ", p).strip(" .-•")
        if len(t) < 2:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t[:160])
    return out[:8]


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": _UA, "Accept": "application/json, text/plain, */*"},
        timeout=httpx.Timeout(timeout, connect=min(4.0, timeout)),
        follow_redirects=True,
    )


def _clean_text(text: str, max_chars: int = 1800) -> str:
    text = html_lib.unescape(text or "")
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return text


# ---------------------------------------------------------------- search -----


def _search_brave(query: str, api_key: str, n: int, timeout: float) -> list[Hit]:
    if not api_key:
        return []
    with _client(timeout) as client:
        resp = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": n},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    hits: list[Hit] = []
    for it in (data.get("web") or {}).get("results") or []:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        hits.append(
            Hit(
                title=(it.get("title") or "").strip(),
                url=url,
                snippet=_clean_text(it.get("description") or "", 420),
                source="brave",
            )
        )
        if len(hits) >= n:
            break
    return hits


def _search_tavily(query: str, api_key: str, n: int, timeout: float) -> list[Hit]:
    if not api_key:
        return []
    with _client(timeout) as client:
        resp = client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": n,
                "include_answer": False,
                "search_depth": "basic",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    hits: list[Hit] = []
    for it in data.get("results") or []:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        hits.append(
            Hit(
                title=(it.get("title") or "").strip(),
                url=url,
                snippet=_clean_text(it.get("content") or "", 420),
                source="tavily",
            )
        )
        if len(hits) >= n:
            break
    return hits


def _search_serper(query: str, api_key: str, n: int, timeout: float) -> list[Hit]:
    if not api_key:
        return []
    with _client(timeout) as client:
        resp = client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            content=json.dumps({"q": query, "num": n}),
        )
        resp.raise_for_status()
        data = resp.json()
    hits: list[Hit] = []
    for it in data.get("organic") or []:
        url = (it.get("link") or "").strip()
        if not url:
            continue
        hits.append(
            Hit(
                title=(it.get("title") or "").strip(),
                url=url,
                snippet=_clean_text(it.get("snippet") or "", 420),
                source="serper",
            )
        )
        if len(hits) >= n:
            break
    return hits


def _search_ddgs(query: str, n: int, timeout: float) -> list[Hit]:
    """DuckDuckGo via the modern ``ddgs`` package (free, no key)."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError:
            log.warning("ddgs not installed; skipping DuckDuckGo search")
            return []

    hits: list[Hit] = []
    # ddgs uses its own HTTP stack; keep the call short.
    with DDGS(timeout=timeout) as ddgs:
        for it in ddgs.text(query, max_results=n) or []:
            url = (it.get("href") or it.get("link") or it.get("url") or "").strip()
            if not url:
                continue
            hits.append(
                Hit(
                    title=(it.get("title") or "").strip(),
                    url=url,
                    snippet=_clean_text(it.get("body") or it.get("snippet") or "", 420),
                    source="ddgs",
                )
            )
            if len(hits) >= n:
                break
    return hits


def _search_wikipedia(query: str, n: int, timeout: float) -> list[Hit]:
    """Wikipedia opensearch + REST summary — reliable free fallback."""
    hits: list[Hit] = []
    with _client(timeout) as client:
        resp = client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": query,
                "limit": max(1, min(n, 5)),
                "namespace": 0,
                "format": "json",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        titles = list(data[1] or []) if isinstance(data, list) and len(data) > 1 else []
        urls = list(data[3] or []) if isinstance(data, list) and len(data) > 3 else []
        for title, url in zip(titles, urls):
            snippet = ""
            try:
                sresp = client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/"
                    f"{urllib.parse.quote(title.replace(' ', '_'))}",
                )
                if sresp.is_success:
                    summary = sresp.json()
                    snippet = _clean_text(summary.get("extract") or "", 420)
                    url = summary.get("content_urls", {}).get("desktop", {}).get("page") or url
            except Exception:
                pass
            hits.append(
                Hit(title=title, url=url, snippet=snippet, source="wikipedia")
            )
            if len(hits) >= n:
                break
    return hits


def _search_ddg_instant(query: str, timeout: float) -> list[Hit]:
    """DuckDuckGo Instant Answer API (definitions / Abstract)."""
    with _client(timeout) as client:
        resp = client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        resp.raise_for_status()
        data = resp.json()
    hits: list[Hit] = []
    abstract = _clean_text(data.get("AbstractText") or "", 500)
    abs_url = (data.get("AbstractURL") or "").strip()
    if abstract and abs_url:
        hits.append(
            Hit(
                title=(data.get("Heading") or query).strip(),
                url=abs_url,
                snippet=abstract,
                source="ddg_instant",
            )
        )
    for topic in (data.get("RelatedTopics") or [])[:3]:
        if not isinstance(topic, dict):
            continue
        text = _clean_text(topic.get("Text") or "", 280)
        url = (topic.get("FirstURL") or "").strip()
        if text and url:
            hits.append(
                Hit(title=text.split(" - ", 1)[0][:80], url=url, snippet=text, source="ddg_instant")
            )
    return hits


def _search_hackernews(query: str, n: int, timeout: float, *, recent_days: int = 0) -> list[Hit]:
    """Hacker News via Algolia — great free signal for what engineers discuss."""
    hits: list[Hit] = []
    params: dict[str, Any] = {
        "query": query,
        "tags": "story",
        "hitsPerPage": max(1, min(n, 20)),
        "numericFilters": "points>20",
    }
    if recent_days > 0:
        cutoff = int(time.time()) - recent_days * 86400
        params["numericFilters"] = f"created_at_i>{cutoff},points>10"
    with _client(timeout) as client:
        resp = client.get(
            "https://hn.algolia.com/api/v1/search",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
    for it in data.get("hits") or []:
        if not isinstance(it, dict):
            continue
        title = (it.get("title") or "").strip()
        object_id = it.get("objectID") or ""
        url = (it.get("url") or "").strip()
        if not url and object_id:
            url = f"https://news.ycombinator.com/item?id={object_id}"
        if not title or not url:
            continue
        points = int(it.get("points") or 0)
        comments = int(it.get("num_comments") or 0)
        created = int(it.get("created_at_i") or 0)
        age_days = max(0.0, (time.time() - created) / 86400) if created else 30.0
        recency_boost = max(0, int(14 - age_days)) * 8
        hits.append(
            Hit(
                title=title[:160],
                url=url,
                snippet=f"HN · {points} pts · {comments} comments · {int(age_days)}d ago",
                source="hackernews",
                score=points + comments // 2 + recency_boost,
            )
        )
        if len(hits) >= n:
            break
    return hits


def _search_arxiv(query: str, n: int, timeout: float) -> list[Hit]:
    """arXiv Atom API — free, authoritative source for AI/ML papers."""
    hits: list[Hit] = []
    clean_q = re.sub(r"[^\w\s-]", " ", query).strip()
    if not clean_q:
        return []
    url = (
        "https://export.arxiv.org/api/query?"
        + urllib.parse.urlencode({
            "search_query": f"all:{clean_q}",
            "max_results": max(1, min(n, 10)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        })
    )
    try:
        with _client(timeout) as client:
            resp = client.get(url)
            if not resp.is_success:
                return []
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
                title = re.sub(r"\s+", " ", title)
                summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
                summary = _clean_text(summary, 500)
                link_url = ""
                for link in entry.findall("atom:link", ns):
                    rel = link.attrib.get("rel")
                    title_attr = link.attrib.get("title")
                    if rel == "alternate" or title_attr == "pdf":
                        link_url = link.attrib.get("href") or link_url
                if title and link_url:
                    hits.append(Hit(title=title, url=link_url, snippet=summary, source="arxiv"))
                if len(hits) >= n:
                    break
    except Exception as e:
        log.debug(f"arXiv search failed: {e}")
    return hits


def _search_huggingface(query: str, n: int, timeout: float) -> list[Hit]:
    """Hugging Face Daily Papers — trending papers & community AI insights."""
    hits: list[Hit] = []
    try:
        with _client(timeout) as client:
            resp = client.get("https://huggingface.co/api/daily_papers")
            if not resp.is_success:
                return []
            data = resp.json()
            q_terms = [t.lower() for t in query.split() if len(t) > 2]
            for item in data if isinstance(data, list) else []:
                paper = item.get("paper") or {}
                title = (paper.get("title") or "").strip()
                summary = _clean_text(paper.get("summary") or "", 420)
                pid = paper.get("id") or ""
                url = f"https://huggingface.co/papers/{pid}" if pid else ""
                blob = f"{title} {summary}".lower()
                matches = sum(1 for term in q_terms if term in blob) if q_terms else 1
                # Require more robust matching so we don't accidentally return random trending 
                # papers just because they contain the word "model" or "llm".
                if q_terms and matches < min(len(q_terms), 2):
                    continue
                if matches > 0 and title and url:
                    hits.append(Hit(title=title, url=url, snippet=summary, source="huggingface", score=matches))
                if len(hits) >= n:
                    break
    except Exception as e:
        log.debug(f"HuggingFace papers search failed: {e}")
    return hits


def _search_muse_grounding(query: str, timeout: float = 20.0) -> list[Hit]:
    """Muse web_search grounding — live sources plus a short synthesis."""
    del timeout
    from . import muse_api

    if not muse_api.api_key():
        return []
    try:
        prompt = (
            f"Research topic: {query}\n\n"
            "Search the web for this topic and provide a detailed technical summary "
            "including exact mechanisms, paper titles/authors, benchmarks, release details, "
            "and real-world trade-offs. Cite sources."
        )
        text, data = muse_api.generate_text(
            prompt,
            model=muse_api.normalize_text_model(get_settings().muse_lite_model),
            use_search=True,
            search_context_size="high",
        )
        hits: list[Hit] = []
        for item in muse_api.search_hits(data):
            hits.append(
                Hit(
                    title=item.get("title") or "Search result",
                    url=item.get("url") or "",
                    snippet=_clean_text(item.get("snippet") or f"Web source for {query[:60]}", 400),
                    source="muse_search",
                )
            )
        if text and len(text) > 100:
            hits.insert(
                0,
                Hit(
                    title=f"Muse search synthesis: {query[:60]}",
                    url=f"https://www.google.com/search?q={urllib.parse.quote(query)}",
                    snippet=_clean_text(text, 2200),
                    source="muse_search",
                    score=10,
                ),
            )
        try:
            from .. import costs

            costs.record(
                provider="muse",
                model=muse_api.normalize_text_model(get_settings().muse_lite_model),
                kind="search",
                in_tokens=0,
                out_tokens=0,
            )
        except Exception:
            pass
        return hits
    except Exception as e:
        log.debug(f"Muse search grounding failed: {e}")
        return []


def _search_muse_grounding(query: str, timeout: float = 20.0) -> list[Hit]:
    """Legacy name. Search now runs through Muse web_search."""
    return _search_muse_grounding(query, timeout)


# Curated AI news / newsletter destinations we bias trending toward.
# Keep queries site-scoped so DDGS/Brave/Serper return on-topic hits.
_AI_NEWS_SOURCES: list[tuple[str, str, str]] = [
    # (id, label, search query)
    ("hackernews", "Hacker News", "AI OR LLM OR GPT OR \"machine learning\""),
    ("aim", "Analytics India Magazine", "site:analyticsindiamag.com (AI OR LLM OR GenAI OR GPU)"),
    ("the_batch", "The Batch", "site:www.deeplearning.ai/the-batch (AI OR LLM)"),
    ("tldr_ai", "TLDR AI", "site:tldr.tech (AI OR LLM OR \"machine learning\")"),
    ("bens_bites", "Ben's Bites", "site:bensbites.com OR site:bensbites.beehiiv.com AI"),
    ("import_ai", "Import AI", "site:importai.substack.com OR \"Import AI\" Jack Clark"),
    ("latent_space", "Latent Space", "site:www.latent.space AI OR LLM OR agents"),
    ("alphasignal", "AlphaSignal", "site:alphasignal.ai AI OR LLM"),
    ("interconnects", "Interconnects", "site:interconnects.ai (LLM OR \"open model\" OR RLHF OR post-training)"),
    ("last_week_in_ai", "Last Week in AI", "site:lastweekin.ai (AI OR LLM OR model)"),
    ("rundown_ai", "The Rundown AI", "site:therundown.ai OR \"The Rundown AI\" (LLM OR OpenAI OR Anthropic)"),
    ("ahead_of_ai", "Ahead of AI", "site:magazine.sebastianraschka.com OR \"Ahead of AI\" Raschka"),
    ("hf_blog", "Hugging Face Blog", "site:huggingface.co/blog (model OR LLM OR release)"),
    ("openai_news", "OpenAI", "site:openai.com/index OR site:openai.com/blog (GPT OR model OR research)"),
    ("anthropic", "Anthropic", "site:anthropic.com/news OR site:anthropic.com/research (Claude OR model)"),
    ("deepmind", "DeepMind", "site:deepmind.google/discover/blog OR site:blog.google/technology/ai (Muse OR model)"),
    ("simonw", "Simon Willison", "site:simonwillison.net (LLM OR GPT OR Claude OR agents)"),
    ("techcrunch_ai", "TechCrunch AI", "site:techcrunch.com (OpenAI OR Anthropic OR LLM OR \"artificial intelligence\")"),
    ("mit_tr", "MIT Tech Review", "site:technologyreview.com (\"artificial intelligence\" OR LLM OR GPT)"),
    ("marktechpost", "Marktechpost", "site:marktechpost.com (LLM OR model OR GenAI)"),
    ("venturebeat_ai", "VentureBeat AI", "site:venturebeat.com/ai (LLM OR OpenAI OR model)"),
    ("reddit_ml", "r/MachineLearning", "site:reddit.com/r/MachineLearning (LLM OR GPT OR \"open source\" OR paper)"),
    ("semianalysis", "SemiAnalysis", "site:semianalysis.com (GPU OR AI OR Nvidia OR training)"),
]


def gather_ai_news_pulse(*, max_hits: int = 24, timeout: float | None = None) -> tuple[str, dict[str, Any]]:
    """Pull a short pulse from HN + AIM + popular AI newsletters.

    Returns a research block string plus metadata (hits, backends).
    """
    s = get_settings()
    if not getattr(s, "topic_research_enabled", True):
        return "", {"enabled": False, "hits": [], "backends": []}

    t_out = float(timeout if timeout is not None else getattr(s, "topic_research_timeout", 8.0) or 8.0)
    brave = (getattr(s, "brave_api_key", None) or "").strip()
    tavily = (getattr(s, "tavily_api_key", None) or "").strip()
    serper = (getattr(s, "serper_api_key", None) or "").strip()

    all_hits: list[Hit] = []
    backends: list[str] = []

    def _hn() -> list[Hit]:
        out: list[Hit] = []
        for q in (
            "AI LLM",
            "GPT OR Claude OR Muse",
            "open source model OR multimodal",
        ):
            try:
                out.extend(_search_hackernews(q, 8, t_out, recent_days=14))
            except Exception as e:
                log.debug(f"HN pulse query failed ({q}): {e}")
        return out

    def _site(qid: str, query: str) -> tuple[list[Hit], list[str]]:
        hits, used = _race_search(
            query, n=3, timeout=t_out, brave_key=brave, tavily_key=tavily, serper_key=serper
        )
        for h in hits:
            if not h.source or h.source in {"ddgs", "brave", "tavily", "serper"}:
                h.source = qid
        return hits, used

    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {}
        futs[pool.submit(_hn)] = "hackernews"
        for qid, _label, query in _AI_NEWS_SOURCES:
            if qid == "hackernews":
                continue
            futs[pool.submit(_site, qid, query)] = qid

        try:
            for fut in as_completed(futs, timeout=t_out + 10):
                name = futs[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    log.debug(f"AI news source {name} failed: {e}")
                    continue
                if name == "hackernews":
                    hits = result or []
                    used = ["hackernews"] if hits else []
                else:
                    hits, used = result if isinstance(result, tuple) else (result or [], [])
                if hits:
                    all_hits.extend(hits)
                    backends.extend(used or [name])
        except TimeoutError:
            log.debug("AI news pulse timed out waiting for some sources")

    # Prefer high-score HN + unique URLs.
    seen: set[str] = set()
    ranked: list[Hit] = []
    for h in sorted(all_hits, key=lambda x: int(x.score or 0), reverse=True):
        key = (h.url or "").rstrip("/").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ranked.append(h)
        if len(ranked) >= max_hits:
            break

    lines = [
        "## AI news pulse (HN · AIM · newsletters · labs · press)",
        f"Sources used: {', '.join(sorted(set(backends))) or 'none'}",
        "",
    ]
    for h in ranked:
        label = h.source or "web"
        score_bit = f" [trend≈{h.score}]" if h.score else ""
        lines.append(f"- ({label}){score_bit} {h.title}")
        if h.snippet:
            lines.append(f"  {h.snippet[:280]}")
        lines.append(f"  {h.url}")
    block = "\n".join(lines)
    return block, {
        "enabled": True,
        "hits": [asdict(h) for h in ranked],
        "backends": sorted(set(backends)),
        "sources": [{"id": i, "label": lab} for i, lab, _ in _AI_NEWS_SOURCES],
    }


def _race_search(
    query: str,
    *,
    n: int,
    timeout: float,
    brave_key: str,
    tavily_key: str,
    serper_key: str,
) -> tuple[list[Hit], list[str]]:
    """Run available search backends concurrently; keep the first solid set.

    Still merges Wikipedia / Instant Answer as soft supplements so educational
    topics always get a definition even when web search is thin.
    """
    backends: list[tuple[str, Any]] = []
    if brave_key:
        backends.append(("brave", lambda: _search_brave(query, brave_key, n, timeout)))
    if tavily_key:
        backends.append(("tavily", lambda: _search_tavily(query, tavily_key, n, timeout)))
    if serper_key:
        backends.append(("serper", lambda: _search_serper(query, serper_key, n, timeout)))
    backends.append(("ddgs", lambda: _search_ddgs(query, n, timeout)))
    backends.append(("ddg_instant", lambda: _search_ddg_instant(query, timeout)))
    backends.append(("wikipedia", lambda: _search_wikipedia(query, min(n, 3), timeout)))
    backends.append(("arxiv", lambda: _search_arxiv(query, min(n, 4), timeout)))
    backends.append(("huggingface", lambda: _search_huggingface(query, min(n, 3), timeout)))
    backends.append(("hackernews", lambda: _search_hackernews(query, min(n, 3), timeout)))
    backends.append(("muse_search", lambda: _search_muse_grounding(query, timeout)))

    used: list[str] = []
    primary: list[Hit] = []
    extras: list[Hit] = []

    with ThreadPoolExecutor(max_workers=len(backends)) as pool:
        future_map = {pool.submit(fn): name for name, fn in backends}
        pending = set(future_map)
        # Prefer the first commercial/ddgs result with ≥2 hits; keep wiki/instant as extras.
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED, timeout=timeout + 2)
            if not done:
                break
            for fut in done:
                name = future_map[fut]
                try:
                    hits = fut.result() or []
                except Exception as e:
                    log.debug(f"search backend {name} failed: {e}")
                    continue
                if not hits:
                    continue
                used.append(name)
                if name in {"wikipedia", "ddg_instant"}:
                    extras.extend(hits)
                elif not primary:
                    primary = hits
                    # Cancel remaining slow backends once we have a solid set.
                    if len(primary) >= 2:
                        for p in pending:
                            p.cancel()
                        pending.clear()
                        break
                else:
                    # Extra commercial hits — take a couple unique URLs.
                    extras.extend(hits[:2])

    # Always try Wikipedia as a soft supplement for teachable definitions,
    # even when a commercial/DDG backend already won the race.
    if "wikipedia" not in used:
        try:
            wiki_hits = _search_wikipedia(query, min(n, 2), timeout)
            if wiki_hits:
                extras.extend(wiki_hits)
                used.append("wikipedia")
        except Exception as e:
            log.debug(f"wikipedia supplement failed: {e}")

    merged: list[Hit] = []
    seen_urls: set[str] = set()
    for h in primary + extras:
        key = h.url.rstrip("/").lower()
        if not key or key in seen_urls:
            continue
        seen_urls.add(key)
        merged.append(h)
        if len(merged) >= n + 2:
            break
    return merged, used


# ---------------------------------------------------------------- fetch ------


def _fetch_jina(url: str, timeout: float) -> str:
    with _client(timeout) as client:
        resp = client.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/plain", "X-Return-Format": "markdown"},
        )
        resp.raise_for_status()
        return _clean_text(resp.text, 2200)


def _fetch_direct(url: str, timeout: float) -> str:
    with _client(timeout) as client:
        resp = client.get(url, headers={"Accept": "text/html,application/xhtml+xml"})
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" not in ctype and "text/" not in ctype and "json" not in ctype:
            return ""
        return _clean_text(resp.text, 2200)


def _fetch_wikipedia_extract(url: str, timeout: float) -> str:
    m = re.search(r"wikipedia\.org/wiki/([^?#]+)", url or "", re.I)
    if not m:
        return ""
    title = urllib.parse.unquote(m.group(1))
    with _client(timeout) as client:
        resp = client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
        )
        if not resp.is_success:
            return ""
        return _clean_text(resp.json().get("extract") or "", 1600)


def _fetch_page(url: str, timeout: float) -> tuple[str, str]:
    """Return (text, backend_name). Tries Jina → Wikipedia → direct."""
    if "wikipedia.org" in (url or "").lower():
        try:
            text = _fetch_wikipedia_extract(url, timeout)
            if len(text) > 80:
                return text, "wikipedia_rest"
        except Exception as e:
            log.debug(f"wiki fetch failed for {url}: {e}")

    for name, fn in (
        ("jina", lambda: _fetch_jina(url, timeout)),
        ("direct", lambda: _fetch_direct(url, timeout)),
    ):
        try:
            text = fn()
            if len(text) > 80:
                return text, name
        except Exception as e:
            log.debug(f"fetch {name} failed for {url}: {e}")
    return "", ""


# --------------------------------------------------------------- public API --


def research_one_topic(
    topic: str,
    *,
    context: str = "",
    max_results: int = 5,
    fetch_pages: int = 3,
    timeout: float = 8.0,
) -> TopicBrief:
    settings = get_settings()
    brief = TopicBrief(topic=topic)

    # Bias the query toward teachable, concrete material for the lesson.
    ctx = (context or "").strip()
    query = f"{topic}"
    if ctx:
        query = f"{topic} {ctx}"[:220]
    # Prefer explanatory pages over pure product landing pages.
    teach_query = f"{query} explained examples"

    hits, used = _race_search(
        teach_query,
        n=max_results,
        timeout=timeout,
        brave_key=(settings.brave_api_key or "").strip(),
        tavily_key=(settings.tavily_api_key or "").strip(),
        serper_key=(settings.serper_api_key or "").strip(),
    )
    # If teach_query was too narrow, retry the bare topic once.
    if len(hits) < 2:
        hits2, used2 = _race_search(
            topic,
            n=max_results,
            timeout=timeout,
            brave_key=(settings.brave_api_key or "").strip(),
            tavily_key=(settings.tavily_api_key or "").strip(),
            serper_key=(settings.serper_api_key or "").strip(),
        )
        used.extend(used2)
        seen = {h.url.rstrip("/").lower() for h in hits}
        for h in hits2:
            key = h.url.rstrip("/").lower()
            if key not in seen:
                hits.append(h)
                seen.add(key)

    brief.hits = hits[: max_results + 2]
    brief.backends_used = list(dict.fromkeys(used))

    # Fetch a couple of pages for richer extract text (parallel).
    to_fetch = [h for h in brief.hits if h.url][: max(0, fetch_pages)]
    if to_fetch:
        with ThreadPoolExecutor(max_workers=min(4, len(to_fetch))) as pool:
            futs = {pool.submit(_fetch_page, h.url, timeout): h for h in to_fetch}
            for fut in as_completed(futs):
                hit = futs[fut]
                try:
                    text, backend = fut.result()
                except Exception as e:
                    log.debug(f"page fetch error: {e}")
                    continue
                if not text:
                    continue
                brief.extracts.append(
                    {
                        "title": hit.title,
                        "url": hit.url,
                        "text": text,
                        "backend": backend,
                    }
                )
                if backend:
                    brief.backends_used.append(f"fetch:{backend}")

    if not brief.hits and not brief.extracts:
        brief.notes.append("no web results (all backends failed or empty)")
    return brief


def format_research_block(briefs: list[TopicBrief], max_chars: int = 24000) -> str:
    """Compact markdown block for the slide-generation prompt."""
    if not briefs:
        return ""
    parts: list[str] = []
    for b in briefs:
        lines = [f"### Topic: {b.topic}"]
        if b.hits:
            lines.append("Sources:")
            for h in b.hits[:6]:
                snip = h.snippet or "(no snippet)"
                lines.append(f"- [{h.source}] {h.title} — {h.url}\n  {snip}")
        if b.extracts:
            lines.append("Page extracts:")
            for ex in b.extracts[:4]:
                lines.append(
                    f"- {ex.get('title') or 'page'} ({ex.get('url')})\n"
                    f"  {_clean_text(ex.get('text') or '', 1800)}"
                )
        if b.notes:
            lines.append("Notes: " + "; ".join(b.notes))
        parts.append("\n".join(lines))
    block = "\n\n".join(parts).strip()
    if len(block) > max_chars:
        block = block[: max_chars - 1].rsplit("\n", 1)[0] + "\n…"
    return block


def research_topics(
    raw_topics: str,
    *,
    context: str = "",
) -> tuple[str, dict[str, Any]]:
    """Research all topics. Returns (prompt_block, metadata_dict)."""
    settings = get_settings()
    if not getattr(settings, "topic_research_enabled", True):
        return "", {"enabled": False, "topics": []}

    topics = parse_topics(raw_topics)
    if not topics:
        return "", {"enabled": True, "topics": []}

    max_results = max(2, int(getattr(settings, "topic_research_max_results", 4) or 4))
    fetch_pages = max(0, int(getattr(settings, "topic_research_fetch_pages", 2) or 2))
    timeout = float(getattr(settings, "topic_research_timeout", 8.0) or 8.0)

    log.info(
        f"researching {len(topics)} topic(s) "
        f"(results={max_results}, fetch_pages={fetch_pages}, timeout={timeout}s)"
    )

    briefs: list[TopicBrief] = []
    # Topics in parallel — each topic already races its own backends.
    with ThreadPoolExecutor(max_workers=min(4, len(topics))) as pool:
        futs = [
            pool.submit(
                research_one_topic,
                t,
                context=context,
                max_results=max_results,
                fetch_pages=fetch_pages,
                timeout=timeout,
            )
            for t in topics
        ]
        for fut in as_completed(futs):
            try:
                briefs.append(fut.result())
            except Exception as e:
                log.warning(f"topic research failed: {e}")

    # Preserve user topic order.
    order = {t: i for i, t in enumerate(topics)}
    briefs.sort(key=lambda b: order.get(b.topic, 99))

    block = format_research_block(briefs)
    meta = {
        "enabled": True,
        "topics": [b.to_dict() for b in briefs],
        "backends": sorted(
            {b for brief in briefs for b in brief.backends_used}
        ),
        "chars": len(block),
    }
    log.success(
        f"topic research ready: {len(briefs)} topic(s), "
        f"{meta['chars']} chars, backends={meta['backends'] or ['none']}"
    )
    return block, meta
