"""Regression checks for the template-free layout synthesizer.

Run:  .venv/bin/python scripts/check_layout_engine.py

Guarantees verified:
  1. every family, for every legal item count and orientation, produces cells
     that stay inside the box and do not collide (40 seeds each);
  2. within one deck no two slides share a geometry signature or repeat the
     previous family;
  3. every video template has a distinct (lead family, motif, heading) fingerprint;
  4. rendering the same deck through all templates never raises.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import layout_engine as L  # noqa: E402
from app.pipeline import content  # noqa: E402
from app.video_options import VIDEO_STYLES  # noqa: E402

BOXES = {"landscape": (1580.0, 590.0), "portrait": (760.0, 1180.0), "square": (760.0, 520.0)}


def check_edges() -> None:
    assert L.make_items(["a", "b"], weights=[float("nan"), 2])[0].weight >= 0.6
    assert L.synthesize([], seed="e", vertical=False, box=BOXES["landscape"]) is None
    one = L.make_items(["only one point"])
    assert L.synthesize(one, seed="e", vertical=False, box=BOXES["landscape"]) is None
    # Portrait skyline must keep short bars on the correct edge, inside the frame.
    items = L.make_items(["low", "mid", "high"], weights=[1, 2, 3])
    for seed in range(30):
        cells, meta = L._fam_skyline(items, 760, 1180, L._rng(f"sky{seed}"))
        assert L.check_cells("skyline", cells, 760, 1180), seed
        if meta["align"] == "top":
            assert all(c.x > 1 for c in cells if c.w < 700), seed
    print("[ok] edges: empty, single item, NaN weight, portrait skyline")


def check_geometry() -> None:
    combos = 0
    for name, (w, h) in BOXES.items():
        for fam in L.FAMILIES:
            lo, hi = L._FIT[fam]
            for n in range(lo, hi + 1):
                if not L.fits(fam, n, h > w):
                    continue
                items = L.make_items([("word " * (2 + (i * 5) % 8)).strip() for i in range(n)])
                for seed in range(40):
                    cells, _ = L._FAM_FN[fam](items, w, h, L._rng(f"chk{seed}"))
                    assert L.check_cells(fam, cells, w, h), (name, fam, n, seed)
                    combos += 1
    print(f"[ok] geometry: {combos} layouts collision-free and in-bounds")


def check_deck_uniqueness() -> None:
    items = L.make_items(["alpha beta", "gamma delta", "epsilon zeta", "eta theta"])
    used: Counter = Counter()
    sigs: set[str] = set()
    last = ""
    seen: list[str] = []
    for i in range(12):
        res = L.synthesize(items, seed=f"deck|{i}", vertical=False, box=BOXES["landscape"],
                           used=used, sigs=sigs, last_family=last)
        assert res, i
        assert res["family"] != last, ("family repeated back-to-back", i)
        assert res["sig"] not in seen, ("duplicate geometry", i)
        seen.append(res["sig"])
        last = res["family"]
    print(f"[ok] deck: 12 slides, {len(set(seen))} unique signatures, no back-to-back family")


def check_templates() -> None:
    profiles = L.template_profiles(list(VIDEO_STYLES))
    prints = Counter(L.template_fingerprint(p) for p in profiles.values())
    assert len(profiles) == len(VIDEO_STYLES)
    assert max(prints.values()) == 1, [k for k, v in prints.items() if v > 1][:3]
    print(f"[ok] templates: {len(profiles)} templates, {len(prints)} unique fingerprints")

    slides = [
        {"heading": "A", "bullets": ["one two", "three four", "five six", "seven eight"],
         "narration": "n", "layout": "bullets"},
        {"heading": "B", "bullets": [], "narration": "First idea is here. Second idea follows. Third idea ends.",
         "layout": "bullets"},
        {"heading": "C", "layout": "stat", "bullets": [], "narration": "n",
         "stats": [{"value": "98%", "label": "accuracy"}, {"value": "12ms", "label": "latency"}]},
        {"heading": "D", "layout": "steps", "bullets": [], "narration": "n",
         "steps": ["prepare", "build", "ship"]},
    ]
    model = {"title": "Check", "slides": slides, "flowchart": ""}
    for key in VIDEO_STYLES:
        html = content.render_slideshow_html(model, {"video_style": key})
        assert 'class="lx ' in html, key
    print(f"[ok] render: {len(VIDEO_STYLES)} templates rendered without error")


def check_agent_harness() -> None:
    from app.agent_memory import CheckpointMemory, HarnessMemory, WorkingMemory
    from app.pipeline.agent_harness import AgentHarness

    # Test working memory
    wm = WorkingMemory("chk_job", "verify harness")
    wm.add_plan_step("s1", "inspect")
    wm.update_plan_step("s1", "completed", "done")
    assert "[✓] s1: inspect -> done" in wm.get_plan_summary()

    # Test checkpoint memory
    cm = CheckpointMemory("chk_job")
    cm.record_turn(1, "test thought", "tool_x", {"a": 1}, {"res": 2}, status="success", elapsed_ms=5.0)
    receipt = cm.get_receipt()
    assert receipt["total_turns"] == 1
    assert receipt["tools_used"] == ["tool_x"]

    # Test long term memory in a temp db
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        mem = HarnessMemory(db_path=Path(tmp.name))
        assert mem.count() >= 5
        mem.store("user_pref", {"style": "neon"}, namespace="preferences", tags="style,neon")
        recalled = mem.recall("neon style", namespace="preferences")
        assert len(recalled) >= 1
        assert recalled[0]["key"] == "user_pref"

    # Test harness tool execution
    harness = AgentHarness("chk_job", options={"video_style": "auto"})
    tools = {t["name"] for t in harness.tools.get_catalog()}
    assert "inspect_document" in tools
    assert "synthesize_visual_layout" in tools
    assert "audit_and_fix_slides" in tools

    res_lx = harness.tools.execute(
        "synthesize_visual_layout", items=["alpha", "beta", "gamma"], vertical=False, seed="test"
    )
    assert res_lx.success is True
    assert res_lx.data["fits"] is True

    print("[ok] agent harness: working memory, checkpoints, persistent memory, and tools verified")


if __name__ == "__main__":
    check_edges()
    check_agent_harness()
    check_geometry()
    check_deck_uniqueness()
    check_templates()
    print("all layout-engine checks passed")
