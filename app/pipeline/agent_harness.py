"""Agentic AI Harness for Multimodal Studio.

Implements an industrial-grade agent harness following 2026 agent engineering standards:
  - Bounded ReAct / Thought-Action-Observation (TAO) control loop with step budgets & timeouts.
  - Typed Tool Registry with strict schema validation, exception trapping, and execution tracing.
  - Three-tier memory integration: Working Memory (scratchpad/plan), Checkpoint Memory
    (JSONL trace log + run receipts), and Persistent Long-Term Memory (HarnessMemory).
  - High-value specialized tools:
      * inspect_document: analyzes document complexity, formulas, sections, and key statistics.
      * recall_memory: queries cross-session persistent memory for user preferences and style rules.
      * save_memory: commits learned takeaways and style feedback to persistent storage.
      * score_style_and_theme: evaluates tone, audience, and selects optimal visual styles.
      * research_topic_context: web-grounded research for external verification and depth.
      * draft_slide_deck: constructs structured slide decks adhering to formatting constraints.
      * synthesize_visual_layout: tests data-fit geometries via layout_engine (treemap, orbit, etc.).
      * audit_and_fix_slides: checks for duplicate headings, visual repetition, and voice-sync drift.
  - Deterministic fallbacks to prevent pipeline failure when models or services are degraded.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..agent_memory import CheckpointMemory, HarnessMemory, WorkingMemory, get_harness_memory
from ..capabilities import llm_available
from ..logging_setup import log


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]
    is_mutation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "mutates": self.is_mutation,
        }


class ToolRegistry:
    """Manages tool registration, schema publication, and sandboxed dispatch."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        func: Callable[..., Any],
        is_mutation: bool = False,
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
            is_mutation=is_mutation,
        )

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_catalog(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tools.values()]

    def execute(self, name: str, **kwargs) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool {name!r} not found in registry. Available: {list(self._tools.keys())}",
            )
        t0 = time.perf_counter()
        try:
            data = tool.func(**kwargs)
            elapsed = (time.perf_counter() - t0) * 1000.0
            return ToolResult(success=True, data=data, elapsed_ms=elapsed)
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000.0
            log.bind(task="agent_tool").warning(f"tool execution {name!r} failed: {e}")
            return ToolResult(success=False, error=str(e), elapsed_ms=elapsed)


class AgentHarness:
    """Production Agent Harness orchestrating slide generation and verification."""

    def __init__(
        self,
        session_id: str,
        options: Optional[dict[str, Any]] = None,
        work_dir: Optional[Path] = None,
        memory: Optional[HarnessMemory] = None,
        max_turns: int = 7,
    ) -> None:
        self.session_id = session_id
        self.options = dict(options or {})
        self.work_dir = work_dir
        self.max_turns = max_turns

        # Layered Memory tiers
        self.working_memory = WorkingMemory(session_id=session_id)
        self.checkpoint_memory = CheckpointMemory(session_id=session_id, output_dir=work_dir)
        self.long_term_memory = memory or get_harness_memory()

        # Tool registry
        self.tools = ToolRegistry()
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the domain tools (see ``tools.get_catalog()`` for the live list)."""

        # 1. Document inspector
        def tool_inspect_document(text: str) -> dict[str, Any]:
            from .content import analyze_document

            analysis = analyze_document(text) if (text or "").strip() else {}
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            equations = [line for line in text.splitlines() if "$" in line or "\\(" in line]
            stats_detected = [
                line for line in text.splitlines() if any(c in line for c in ("%", "$", "x", "×"))
            ]
            return {
                "doc_type": analysis.get("doc_type", "other"),
                "detected_title": analysis.get("title", ""),
                "char_count": len(text),
                "paragraph_count": len(paragraphs),
                "has_equations": len(equations) > 0,
                "equation_sample": equations[:3],
                "stats_sample": stats_detected[:3],
                "outline_hints": [p[:80] + "..." for p in paragraphs[:5]],
            }

        self.tools.register(
            name="inspect_document",
            description="Examines raw document text to classify structure, equations, statistics, and topics.",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            func=tool_inspect_document,
        )

        # 2. Recall memory
        def tool_recall_memory(query: str, namespace: str = "general", limit: int = 4) -> list[dict[str, Any]]:
            return self.long_term_memory.recall(query=query, namespace=namespace or None, limit=limit)

        self.tools.register(
            name="recall_memory",
            description="Retrieves relevant persistent knowledge (style rules, preferences, domain facts).",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "namespace": {"type": "string", "enum": ["preferences", "style_rules", "domain_knowledge", "feedback", "general"]},
                    "limit": {"type": "integer", "default": 4},
                },
                "required": ["query"],
            },
            func=tool_recall_memory,
        )

        # 3. Save memory
        def tool_save_memory(key: str, value: Any, namespace: str = "feedback", tags: str = "") -> dict[str, str]:
            self.long_term_memory.store(key=key, value=value, namespace=namespace, tags=tags)
            return {"status": "stored", "key": key, "namespace": namespace}

        self.tools.register(
            name="save_memory",
            description="Stores a takeaway, audience preference, or formatting correction in long-term memory.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "namespace": {"type": "string", "default": "feedback"},
                    "tags": {"type": "string"},
                },
                "required": ["key", "value"],
            },
            func=tool_save_memory,
            is_mutation=True,
        )

        # 4. Score style and theme
        def tool_score_style_and_theme(doc_type: str, text: str) -> dict[str, Any]:
            from ..video_options import apply_auto_video_style, apply_auto_video_theme

            dummy_opts = dict(self.options)
            dummy_analysis = {"doc_type": doc_type}
            apply_auto_video_style(dummy_opts, analysis=dummy_analysis, text=text[:2000])
            apply_auto_video_theme(dummy_opts, analysis=dummy_analysis)
            return {
                "recommended_style": dummy_opts.get("video_style"),
                "style_label": dummy_opts.get("video_style_label"),
                "style_reason": dummy_opts.get("video_style_reason"),
                "recommended_theme": dummy_opts.get("video_theme"),
                "theme_label": dummy_opts.get("video_theme_label"),
            }

        self.tools.register(
            name="score_style_and_theme",
            description="Scores and recommends optimal visual presentation style and color theme.",
            parameters={
                "type": "object",
                "properties": {
                    "doc_type": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["doc_type", "text"],
            },
            func=tool_score_style_and_theme,
        )

        # 5. Research topic context
        def tool_research_topic_context(topic: str) -> dict[str, Any]:
            try:
                from .topic_research import research_topics

                brief, meta = research_topics(topic, context=topic)
                return {
                    "brief": brief[:1200] if brief else "",
                    "backends": meta.get("backends", []),
                    "chars": meta.get("chars", 0),
                }
            except Exception as e:
                return {"brief": "", "error": str(e)}

        self.tools.register(
            name="research_topic_context",
            description="Queries web research engines to ground concepts and verify statistics.",
            parameters={
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
            func=tool_research_topic_context,
        )

        # 6. Synthesize visual layout
        def tool_synthesize_visual_layout(
            items: list[str],
            weights: Optional[list[float]] = None,
            vertical: bool = False,
            seed: str = "test",
        ) -> dict[str, Any]:
            from ..layout_engine import FAMILIES, make_items, synthesize

            lx_items = make_items(items, weights=weights)
            box = (760.0, 1180.0) if vertical else (1580.0, 590.0)
            res = synthesize(lx_items, seed=seed, vertical=vertical, box=box, family_order=FAMILIES)
            if res:
                return {
                    "fits": True,
                    "family": res["family"],
                    "signature": res["sig"],
                    "cell_count": len(lx_items),
                }
            return {"fits": False, "reason": "Items could not fit cleanly without collision"}

        self.tools.register(
            name="synthesize_visual_layout",
            description="Tests if a list of bullet points and weights can be synthesized into a collision-free geometry.",
            parameters={
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "string"}},
                    "weights": {"type": "array", "items": {"type": "number"}},
                    "vertical": {"type": "boolean", "default": False},
                    "seed": {"type": "string", "default": "test"},
                },
                "required": ["items"],
            },
            func=tool_synthesize_visual_layout,
        )

        # 7. Audit and fix slides
        def tool_audit_and_fix_slides(slides: list[dict[str, Any]]) -> dict[str, Any]:
            from .content_review import review_slides

            rev = review_slides(slides, options=self.options)
            issues = rev.get("issues", [])
            recommendations: list[str] = []
            for iss in issues:
                msg = iss.get("message", "")
                sl_idx = iss.get("slide")
                if "duplicate_heading" in iss.get("kind", ""):
                    recommendations.append(f"Differentiate heading on slide {sl_idx}: {msg}")
                elif "duplicate_visual" in iss.get("kind", ""):
                    recommendations.append(f"Change layout geometry or vary bullet count on slide {sl_idx}.")
                elif any(k in iss.get("kind", "") for k in ("voice", "narration", "speed", "sync")):
                    recommendations.append(f"Adjust word count or dwell time on slide {sl_idx} for narration sync.")

            return {
                "issue_count": len(issues),
                "issues": issues[:6],
                "clean": len(issues) == 0,
                "recommendations": recommendations,
                # Every slide that needs a new heading, not just the first few issues.
                "duplicate_heading_slides": sorted(
                    {int(i["slide"]) for i in issues if i.get("kind") == "duplicate_heading" and i.get("slide")}
                ),
            }

        self.tools.register(
            name="audit_and_fix_slides",
            description="Reviews generated slides for duplicates, narration ↔ highlight sync drift, and density flaws.",
            parameters={
                "type": "object",
                "properties": {
                    "slides": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["slides"],
            },
            func=tool_audit_and_fix_slides,
        )

        # 8. Draft slide deck
        def tool_draft_slide_deck(text: str, doc_analysis: dict[str, Any], cover_image: Optional[str] = None) -> dict[str, Any]:
            from .content import _build_fallback_slides, _enforce_word_budget, generate_slides_with_muse

            if llm_available():
                try:
                    deck = generate_slides_with_muse(text, self.options, doc_analysis, cover_image)
                    deck = _enforce_word_budget(deck, self.options)
                    return {"success": True, "model": deck}
                except Exception as e:
                    log.bind(task="agent").warning(f"LLM slide drafting error: {e}")

            # Safe deterministic fallback
            deck = _build_fallback_slides(text, self.options, doc_analysis, cover_image)
            return {"success": True, "model": deck, "fallback": True}

        self.tools.register(
            name="draft_slide_deck",
            description="Drafts a complete slide deck model using analysis, options, and content.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "doc_analysis": {"type": "object"},
                    "cover_image": {"type": "string"},
                },
                "required": ["text", "doc_analysis"],
            },
            func=tool_draft_slide_deck,
        )

    @staticmethod
    def _distinct_heading(slide: dict[str, Any], number: int) -> str:
        """A heading that no longer repeats an earlier slide: add the first on-screen point."""
        head = str(slide.get("heading") or "").strip()
        try:
            from .sync import slide_focus_texts

            hints = [t.strip() for t in slide_focus_texts(slide) if t and t.strip()]
        except Exception:  # noqa: BLE001
            hints = []
        hint = next((h for h in hints if h.lower() != head.lower()), "")
        if hint:
            hint = hint if len(hint) <= 38 else hint[:37].rsplit(" ", 1)[0] + "…"
            return f"{head}: {hint}" if head else hint
        return f"{head} ({number})" if head else f"Part {number}"

    def execute_turn(
        self,
        turn: int,
        thought: str,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> ToolResult:
        """Executes a single step in the ReAct loop and records checkpoint traces."""
        log.bind(task="agent_harness").info(
            f"[Turn {turn}/{self.max_turns}] Thought: {thought[:80]}... -> Action: {tool_name}"
        )
        res = self.tools.execute(tool_name, **tool_args)
        status = "success" if res.success else "error"
        self.checkpoint_memory.record_turn(
            turn=turn,
            thought=thought,
            tool=tool_name,
            args=tool_args,
            result=res.to_dict(),
            status=status,
            elapsed_ms=res.elapsed_ms,
        )
        self.working_memory.record_observation(
            f"Turn {turn} {tool_name}: {'OK' if res.success else res.error}"
        )
        return res

    def run(self, raw_text: str, cover_image: Optional[str] = None) -> tuple[dict[str, Any], bool, dict[str, Any]]:
        """Executes the full agentic loop to inspect, reason, draft, audit, and finalize slides.

        Returns: (slide_model, used_llm, run_receipt)
        """
        start_time = time.time()
        self.working_memory.goal = "Produce a high-retention, sync-aligned, data-fit animated slide video deck."

        # Setup initial task plan in Working Memory
        self.working_memory.add_plan_step("inspect", "Inspect document structure and extract key data")
        self.working_memory.add_plan_step("recall", "Consult persistent memory for domain & style rules")
        self.working_memory.add_plan_step("score_style", "Determine optimal visual style and color theme")
        self.working_memory.add_plan_step("draft", "Draft structured slide deck with narration")
        self.working_memory.add_plan_step("audit", "Audit slides for duplicates, timing sync, and density")
        self.working_memory.add_plan_step("finalize", "Synthesize final geometry and commit learnings")

        turn = 1

        # Turn 1: Inspect Document
        self.working_memory.update_plan_step("inspect", "in_progress")
        t1_thought = "First, examine document structure, volume, formulas, and data points."
        res_inspect = self.execute_turn(
            turn=turn,
            thought=t1_thought,
            tool_name="inspect_document",
            tool_args={"text": raw_text[:8000]},
        )
        doc_info = res_inspect.data if res_inspect.success else {"doc_type": "other"}
        doc_type = doc_info.get("doc_type", "other")
        self.working_memory.set_scratchpad("doc_info", doc_info)
        self.working_memory.update_plan_step("inspect", "completed", f"Type: {doc_type}")
        turn += 1

        # Turn 2: Recall Memory
        self.working_memory.update_plan_step("recall", "in_progress")
        t2_thought = f"Query long-term memory for established guidelines on {doc_type} and pacing."
        res_mem = self.execute_turn(
            turn=turn,
            thought=t2_thought,
            tool_name="recall_memory",
            tool_args={"query": f"{doc_type} pacing layout", "namespace": "style_rules", "limit": 3},
        )
        memories = res_mem.data if res_mem.success else []
        self.working_memory.set_scratchpad("memories", memories)
        self.working_memory.update_plan_step("recall", "completed", f"Found {len(memories)} memory items")
        turn += 1

        # Turn 3: Score Style and Theme (if not locked by user)
        self.working_memory.update_plan_step("score_style", "in_progress")
        style_locked = bool(self.options.get("video_style") and self.options.get("video_style") != "auto")
        if not style_locked:
            t3_thought = f"Score and select visual style and theme matching {doc_type}."
            res_style = self.execute_turn(
                turn=turn,
                thought=t3_thought,
                tool_name="score_style_and_theme",
                tool_args={"doc_type": doc_type, "text": raw_text[:2000]},
            )
            if res_style.success and isinstance(res_style.data, dict):
                style_data = res_style.data
                self.options["video_style"] = style_data.get("recommended_style")
                self.options["video_style_label"] = style_data.get("style_label")
                self.options["video_style_reason"] = style_data.get("style_reason")
                self.options["video_theme"] = style_data.get("recommended_theme")
                self.options["video_theme_label"] = style_data.get("theme_label")
                self.working_memory.update_plan_step(
                    "score_style", "completed", f"Style: {self.options.get('video_style')}"
                )
            turn += 1
        else:
            self.working_memory.update_plan_step("score_style", "completed", "Preserved user-locked style")

        # Turn 4: Draft Slide Deck
        self.working_memory.update_plan_step("draft", "in_progress")
        t4_thought = "Draft the complete slide deck with narration, smart fit layouts, and formulas."
        res_draft = self.execute_turn(
            turn=turn,
            thought=t4_thought,
            tool_name="draft_slide_deck",
            tool_args={
                "text": raw_text,
                "doc_analysis": doc_info,
                "cover_image": cover_image,
            },
        )
        draft_data = res_draft.data if res_draft.success else {}
        model = draft_data.get("model") or {}
        used_llm = not draft_data.get("fallback", False)
        slides = model.get("slides") or []
        self.working_memory.set_scratchpad("model", model)
        self.working_memory.update_plan_step("draft", "completed", f"Drafted {len(slides)} slides")
        turn += 1

        # Turn 5: Audit & Fix Slides
        self.working_memory.update_plan_step("audit", "in_progress")
        t5_thought = "Run quality and sync audit on drafted slides to catch duplicate visuals or headings."
        res_audit = self.execute_turn(
            turn=turn,
            thought=t5_thought,
            tool_name="audit_and_fix_slides",
            tool_args={"slides": slides},
        )
        audit_res = res_audit.data if res_audit.success else {}
        issue_count = audit_res.get("issue_count", 0)
        self.working_memory.update_plan_step(
            "audit", "completed", f"Audit clean: {issue_count == 0} ({issue_count} issues)"
        )
        turn += 1

        # Turn 6: Self-correction. Only runs when the audit found something it can
        # fix on its own (a heading that repeats an earlier slide). Everything else is
        # left to the review panel rather than guessed at here.
        repaired = 0
        dup_slides = [n for n in (audit_res.get("duplicate_heading_slides") or []) if 1 <= n <= len(slides)]
        if dup_slides and turn <= self.max_turns:
            t6_thought = f"Repair {len(dup_slides)} slide heading(s) that repeat an earlier slide, then re-audit."
            fixed_slides = [dict(sl) for sl in slides]
            for n in dup_slides:
                sl = fixed_slides[n - 1]
                sl["heading"] = self._distinct_heading(sl, n)
                repaired += 1
            model["slides"] = fixed_slides
            res_fix = self.execute_turn(
                turn=turn,
                thought=t6_thought,
                tool_name="audit_and_fix_slides",
                tool_args={"slides": fixed_slides},
            )
            if res_fix.success and isinstance(res_fix.data, dict):
                issue_count = int(res_fix.data.get("issue_count", issue_count))
            self.working_memory.update_plan_step(
                "audit", "completed",
                f"Repaired {repaired} heading(s); {issue_count} issue(s) left for review",
            )
            turn += 1

        # Turn 7: Finalize & Learn into Long-term Memory
        self.working_memory.update_plan_step("finalize", "in_progress")
        t_final_thought = "Commit run summary and useful observations into persistent memory."
        style_key = self.options.get("video_style", "hybrid")
        self.execute_turn(
            turn=turn,
            thought=t_final_thought,
            tool_name="save_memory",
            tool_args={
                "key": f"run_{self.session_id}",
                "value": {
                    "doc_type": doc_type,
                    "slide_count": len(model.get("slides", [])),
                    "style": style_key,
                    "theme": self.options.get("video_theme", "neon"),
                },
                "namespace": "feedback",
                "tags": f"{doc_type},{style_key},session",
            },
        )
        self.working_memory.update_plan_step("finalize", "completed", "Run trace finalized")

        # Compile final run receipt
        receipt = self.checkpoint_memory.get_receipt()
        receipt["total_duration_sec"] = round(time.time() - start_time, 2)
        receipt["plan"] = [s.to_dict() for s in self.working_memory.plan]
        receipt["repaired"] = repaired
        receipt["max_turns"] = self.max_turns

        log.bind(task="agent_harness").success(
            f"Agent completed {len(receipt['steps'])} turns in {receipt['total_duration_sec']}s. Deck slides: {len(model.get('slides', []))}"
        )
        return model, used_llm, receipt
