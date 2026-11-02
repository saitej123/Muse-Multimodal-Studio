"""Design families for the slide HTML.

Earlier the 80+ "styles" were mostly palette swaps on one layout. Here every
style resolves to one of six *design families*. A family changes structure, not
just colour: where the title sits, how the content block is carved up, the
motion language, the decoration and the fonts.

    split     editorial two-column: title rail on the side, hairline-ruled content
    band      title band across the top, accent-topped cards, diagonal hatch
    sketch    hand-drawn: dotted paper, wobbly outlines, drawn underline + doodles
    poster    huge condensed type, ink-black cards with hard offset shadows
    bento     mosaic of rounded tiles that fills the whole frame
    notebook  ruled paper with margin line, marker highlight, checkbox lines

Shared rules:
  * One unit (``1em`` = 26px x ``--fit``). Every size is in em so a slide can be
    scaled as a whole. ``eduFit`` picks the biggest ``--fit`` that still fits, so
    sparse slides grow into the space and dense ones shrink instead of clipping.
  * Content blocks stretch (``1fr`` rows) so the frame is used end to end.
  * Subtitles are small and unobtrusive.
  * Colours still come from the chosen theme (``--ink --bg --panel --a --b``).

Reference canvas 1920x1080; vertical and square have their own sizing.
"""
from __future__ import annotations

import re

from .edu_families_extra import (
    EXTRA_BODY_WEIGHT,
    EXTRA_FAMILY_INFO,
    EXTRA_FAMILY_MAP,
    EXTRA_FONTS,
    build_css as _extra_css,
)

# Style key -> design family. Keys not listed are spread by hash so every
# style still lands on a distinct-feeling layout. This is the single source of
# truth: the renderer, the style picker and the admin preview all read it.
_BASE_FAMILY_MAP = {
    "sketch": ("whiteboard", "playful", "teardown", "folk_freq", "chalk"),
    "notebook": ("tutorial", "explainer", "notion", "slides", "agenda", "minimal"),
    "split": ("editorial", "documentary", "keynote", "pitch", "corporate", "geo_navy",
              "coral_split", "split_media", "proof_duo", "swiss_pulse", "velvet_std"),
    "band": ("broadcast", "lower_third", "saas", "process", "timeline_rail", "kpi_strip",
             "device", "glass", "modern", "terminal", "blueprint"),
    "poster": ("bold", "kinetic", "kinetic_center", "big_stat", "quote_pull", "cinematic",
               "neon", "maximalist", "promo_sprint", "caption_pop", "hybrid_kinetic", "deconstructed"),
    "bento": ("bento", "cards", "dataviz", "mosaic", "stack_cards", "gamma", "hybrid_data",
              "chart_race", "blush_soft", "hybrid", "hybrid_story", "data_drift", "soft_signal"),
}
# New families first: a style listed there wins over the original six.
EDU_FAMILY_MAP = {**EXTRA_FAMILY_MAP, **_BASE_FAMILY_MAP}
# Picker order: teaching -> editorial -> business -> bold/story -> dev.
EDU_FAMILIES = ("sketch", "notebook", "chalk", "split", "magazine", "band", "glass", "bento",
                "poster", "pop", "cinema", "terminal")

# What the UI shows for each family (order = picker order).
FAMILY_INFO = {
    "sketch": {
        "label": "Whiteboard",
        "blurb": "Hand-drawn: dotted paper, wobbly outlines, underlines and doodles that draw themselves.",
        "uses": "Explaining, maths, step-by-step teaching",
        "flagship": "whiteboard",
    },
    "notebook": {
        "label": "Notebook",
        "blurb": "Ruled paper with a margin line, a marker that sweeps the point being spoken, checkbox lines.",
        "uses": "Revision, tutorials, how-tos",
        "flagship": "tutorial",
    },
    "split": {
        "label": "Editorial",
        "blurb": "Two columns: a title rail on the side and hairline-ruled content, in a serif voice.",
        "uses": "Essays, papers, documentary-style lessons",
        "flagship": "editorial",
    },
    "band": {
        "label": "Broadcast",
        "blurb": "A title band across the top, accent-topped cards, diagonal hatch. Reads like a news explainer.",
        "uses": "Product demos, processes, timelines",
        "flagship": "broadcast",
    },
    "poster": {
        "label": "Poster",
        "blurb": "Huge condensed type, ink-black cards with hard offset shadows. Built for vertical video.",
        "uses": "Shorts, Reels, big claims and stats",
        "flagship": "bold",
    },
    "bento": {
        "label": "Bento",
        "blurb": "A mosaic of rounded tiles that fills the whole frame, so dense content still looks tidy.",
        "uses": "Dashboards, comparisons, data-rich chapters",
        "flagship": "bento",
    },
}
FAMILY_INFO.update(EXTRA_FAMILY_INFO)
# Re-order to the picker order.
FAMILY_INFO = {k: FAMILY_INFO[k] for k in EDU_FAMILIES}


def edu_family(style_key: str) -> tuple[str, int]:
    """(family, font variant 0-3) for a style key."""
    import zlib

    key = str(style_key or "hybrid").strip().lower()
    for fam, keys in EDU_FAMILY_MAP.items():
        if key in keys:
            return fam, zlib.crc32(key.encode()) % 4
    h = zlib.crc32(key.encode())
    return EDU_FAMILIES[h % len(EDU_FAMILIES)], (h >> 3) % 4


# (heading font, heading weight, body font)
_FONTS = {
    "split": [("Fraunces", 700, "DM Sans"), ("Playfair Display", 700, "Inter"),
              ("Instrument Serif", 400, "Figtree"), ("Newsreader", 600, "Work Sans")],
    "band": [("Poppins", 700, "Inter"), ("Outfit", 700, "DM Sans"),
             ("Plus Jakarta Sans", 800, "Figtree"), ("Sora", 700, "Manrope")],
    "sketch": [("Caveat", 700, "Kalam"), ("Gloria Hallelujah", 400, "Patrick Hand"),
               ("Kalam", 700, "Patrick Hand"), ("Patrick Hand", 400, "Kalam")],
    "poster": [("Anton", 400, "Archivo"), ("Oswald", 700, "Barlow"),
               ("Bricolage Grotesque", 800, "Space Grotesk"), ("Syne", 800, "Archivo")],
    "bento": [("Space Grotesk", 700, "Inter"), ("Sora", 700, "Figtree"),
              ("Manrope", 800, "DM Sans"), ("Bricolage Grotesque", 700, "Work Sans")],
    "notebook": [("Permanent Marker", 400, "Patrick Hand"), ("Caveat", 700, "Kalam"),
                 ("Kalam", 700, "Nunito"), ("Gloria Hallelujah", 400, "Patrick Hand")],
}
_FONTS.update(EXTRA_FONTS)
_BODY_WEIGHT = {"sketch": 400, "notebook": 400, "poster": 600, **EXTRA_BODY_WEIGHT}


def _font_css() -> str:
    out = []
    for fam, rows in _FONTS.items():
        for i, (hf, hw, bf) in enumerate(rows):
            out.append(
                f'body.edu[data-edu="{fam}"][data-efont="{i}"] '
                f'{{ --hf:"{hf}", system-ui, sans-serif; --hw:{hw}; --bf:"{bf}", system-ui, sans-serif; '
                f'--bw:{_BODY_WEIGHT.get(fam, 500)}; }}'
            )
    return "\n".join(out)


# NOTE: written with plain braces. ``_important`` adds !important to every
# declaration so these rules always beat the legacy per-style stylesheets.
_P = "html body.edu"

_RAW = r"""
@@ { font-family:var(--bf); }
@@ .slide .bg { background:var(--bg); }
@@ .slide .bg::before { opacity:0; }
@@ .slide .bg::after { opacity:0; }
@@ .frame-orn, @@ .motif, @@ .kicker { display:none; }

@@ .brand-tag { top:24px; left:auto; right:96px; font-size:18px; font-weight:600; color:var(--muted); font-family:var(--bf); opacity:.9; }
@@ .brand-tag .dot { width:12px; height:12px; border-radius:4px; box-shadow:none; }
@@ .progress { height:5px; box-shadow:none; }

@@ .stage-wrap { padding:76px 96px 104px; align-items:stretch; justify-content:stretch; }
@@ .scene {
  max-width:none; width:100%; height:100%; max-height:100%; margin:0; text-align:left;
  display:flex; flex-direction:column; align-items:stretch; overflow:visible;
  font-size:calc(var(--fit, 1) * 26px); font-family:var(--bf); font-weight:var(--bw, 500);
}
@@ h2 {
  font-family:var(--hf); font-weight:var(--hw, 700); font-size:2.6em; line-height:1.06; letter-spacing:-.02em;
  margin:0 0 .45em; max-width:100%; text-align:left; text-transform:none; text-wrap:balance; color:var(--ink);
  padding:0; background:none; border:0; flex:none;
}
@@ h2::before, @@ h2::after { content:none; }
@@ h2 .accent { color:var(--a); background:none; box-shadow:none; padding:0; }
@@ .h-under { display:none; }
@@ .decos { display:none; }

@@ .body {
  flex:1 1 auto; min-height:0; display:grid; grid-template-columns:minmax(0,1fr); grid-template-rows:minmax(0,1fr);
  gap:.8em; align-content:stretch; align-items:stretch; justify-content:stretch; overflow:visible; width:100%;
}
@@ .body.two { grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:1.4em; }
@@ .body > *, @@ .text { min-width:0; min-height:0; height:100%; width:100%; max-width:none; }
@@ .body > .v-chips, @@ .body > .eq-list, @@ .body > .bullets.compact { height:auto; align-self:end; }
@@ .reveal { min-width:0; }

/* ---------- card surface shared by every family ---------- */
@@ .bullets li, @@ .v-card, @@ .v-tile, @@ .v-rail li, @@ .v-agenda li, @@ .v-col li, @@ .steps .step,
@@ .cmp-col, @@ .stat-card, @@ .mx-card, @@ .flow-node, @@ .hub-card, @@ .eq {
  background:var(--cardbg); border:var(--bd) solid var(--line); border-radius:var(--r);
  box-shadow:var(--sh); backdrop-filter:none; min-height:0; max-width:100%; flex:none; position:relative;
}

/* ---------- content blocks stretch to fill ---------- */
@@ .bullets { display:grid; grid-auto-rows:1fr; gap:.55em; height:100%; width:100%; max-width:none; margin:0; padding:0; list-style:none; }
@@ .bullets.grid { grid-template-columns:repeat(2, minmax(0,1fr)); }
@@ .bullets li { display:flex; align-items:center; gap:.7em; padding:.45em 1em; }
@@ .b-mark { width:.6em; height:.6em; box-shadow:none; flex:none; }
@@ .b-mark.check { width:1.4em; height:1.4em; border-radius:.4em; }
@@ .b-text { font-size:1.3em; line-height:1.28; font-weight:var(--bw, 500); color:var(--ink); max-width:100%; flex:1 1 auto; min-width:0; height:auto; max-height:none; }

@@ .v-cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(10em, 1fr)); grid-auto-rows:1fr; gap:.7em; height:100%; }
@@ .v-bento { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); grid-auto-rows:1fr; gap:.7em; height:100%; }
@@ .v-split { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:.9em; height:100%; }
@@ .v-col, @@ .v-rail, @@ .v-agenda { display:grid; grid-auto-rows:1fr; gap:.6em; height:100%; margin:0; padding:0; list-style:none; width:100%; max-width:none; }
@@ .v-spot { display:flex; flex-direction:column; justify-content:center; gap:1em; height:100%; width:100%; }
@@ .v-lead { margin:0; font-size:2.1em; line-height:1.15; font-weight:var(--hw, 700); font-family:var(--hf); color:var(--ink); max-width:100%; text-wrap:balance; }
@@ .v-chips { display:flex; flex-wrap:wrap; gap:.6em; margin:0; padding:0; list-style:none; }
@@ .v-chip { padding:.4em 1.1em; font-size:1.15em; border-radius:999px; color:var(--ink); border:1px solid color-mix(in srgb, var(--a) 40%, var(--line)); background:color-mix(in srgb, var(--a) 10%, var(--bg)); box-shadow:none; }
@@ .v-card, @@ .v-tile { display:flex; flex-direction:column; align-items:flex-start; justify-content:center; gap:.45em; padding:.9em 1.1em; }
@@ .v-rail li, @@ .v-agenda li, @@ .v-col li { display:flex; flex-direction:row; align-items:center; justify-content:flex-start; text-align:left; gap:.8em; padding:.4em 1em; height:auto; }
@@ .v-t { font-size:1.2em; line-height:1.3; font-weight:var(--bw, 500); color:var(--ink); height:auto; max-height:none; min-width:0; overflow-wrap:break-word; }
@@ .v-idx, @@ .v-num, @@ .v-k, @@ .v-check, @@ .v-dot {
  flex:none; display:inline-grid; place-items:center; min-width:2em; height:2em; padding:0 .4em; border-radius:.6em;
  font-size:.8em; font-weight:800; color:var(--bg); background:var(--a); border:0; font-family:var(--hf); letter-spacing:0;
}

/* timeline */
@@ .v-time { position:relative; display:grid; grid-template-columns:repeat(var(--n, 4), minmax(0,1fr)); gap:.9em; align-items:stretch; height:100%; padding-top:3.1em; }
@@ .v-line { position:absolute; left:0; top:1.5em; width:100%; height:.4em; overflow:visible; }
@@ .v-line path { stroke:var(--a); stroke-width:3; fill:none; stroke-dasharray:1; stroke-dashoffset:calc(1 - var(--p, 1)); vector-effect:non-scaling-stroke; stroke-linecap:round; }
@@ .v-tl { display:flex; flex-direction:column; justify-content:flex-start; align-items:flex-start; gap:.5em; padding:1em 1em; }
@@ .v-tl .v-dot { position:absolute; top:-2.7em; left:.8em; width:2.1em; border-radius:50%; font-size:.85em; }
/* stairs */
@@ .v-stairs { display:grid; grid-template-columns:repeat(var(--n, 4), minmax(0,1fr)); gap:.6em; align-items:end; height:100%; }
@@ .v-st { height:calc(32% + 68% * ((var(--k, 0) + 1) / var(--n, 4))); display:flex; flex-direction:column; align-items:flex-start; justify-content:flex-start; gap:.5em; padding:.8em 1em; }
/* sticky notes */
@@ .v-notes { display:grid; grid-template-columns:repeat(auto-fit, minmax(9em, 1fr)); grid-auto-rows:1fr; gap:1em; height:100%; padding:.4em; }
@@ .v-note { rotate:calc((var(--k, 0) - 1.5) * 1.5deg); background:#fff3a3; border:0; border-radius:.2em; box-shadow:.12em .22em .5em rgba(0,0,0,.22); justify-content:center; padding:1.1em 1em .9em; }
@@ .v-note:nth-child(4n+2) { background:#ffd3dc; }
@@ .v-note:nth-child(4n+3) { background:#cdeeff; }
@@ .v-note:nth-child(4n+4) { background:#d6f5c4; }
@@ .v-note .v-t { color:#1f1f1f; }
@@ .v-pin { position:absolute; top:-.35em; left:50%; width:.8em; height:.8em; margin-left:-.4em; border-radius:50%; background:var(--a); box-shadow:0 .1em .2em rgba(0,0,0,.3); }

/* steps / compare / stats / quote / hook / bars / matrix / flow */
@@ .steps { display:grid; grid-auto-rows:1fr; gap:.6em; height:100%; width:100%; max-width:none; margin:0; padding:0; list-style:none; }
@@ .steps .step { display:flex; align-items:center; gap:.9em; padding:.4em 1em; }
@@ .steps .step::after { display:none; }
@@ .step-num { flex:none; width:2.1em; height:2.1em; border-radius:50%; font-size:.9em; font-weight:800; color:var(--bg); background:var(--a); border:0; font-family:var(--hf); display:grid; place-items:center; }
@@ .step-text { font-size:1.3em; line-height:1.28; font-weight:var(--bw, 500); color:var(--ink); }
@@ .compare { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); gap:.8em; height:100%; width:100%; align-items:stretch; }
@@ .cmp-col { padding:1em 1.2em; display:flex; flex-direction:column; justify-content:center; }
@@ .cmp-title { font-size:1.6em; font-weight:var(--hw, 700); font-family:var(--hf); margin-bottom:.5em; color:var(--ink); }
@@ .cmp-col ul { margin:0; padding:0; }
@@ .cmp-col li { font-size:1.2em; line-height:1.35; margin-bottom:.4em; padding-left:1.1em; color:var(--ink); background:none; border:0; box-shadow:none; }
@@ .cmp-col li::before { width:.4em; height:.4em; top:.55em; }
@@ .cmp-vs { width:2.4em; height:2.4em; font-size:.8em; font-family:var(--hf); font-weight:800; align-self:center; }
@@ .stat-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(9em, 1fr)); grid-auto-rows:1fr; gap:.8em; height:100%; width:100%; justify-content:stretch; }
@@ .stat-card { display:flex; flex-direction:column; justify-content:center; align-items:flex-start; text-align:left; padding:.8em 1.1em; max-width:none; flex:none; }
@@ .stat-value { font-size:3.8em; line-height:1; font-weight:var(--hw, 700); font-family:var(--hf); color:var(--a); text-shadow:none; letter-spacing:-.03em; }
@@ .stat-label { font-family:var(--bf); font-size:1.15em; line-height:1.3; font-weight:var(--bw, 500); color:var(--muted); letter-spacing:0; margin-top:.4em; }
@@ .quote { height:100%; max-width:none; text-align:left; padding:.2em 0 .2em 1.1em; border-left:.3em solid var(--a); margin:0; display:flex; flex-direction:column; justify-content:center; }
@@ .quote .q-mark { display:none; }
@@ .quote p { font-size:2.3em; line-height:1.15; font-weight:var(--hw, 700); font-family:var(--hf); -webkit-line-clamp:7; }
@@ .hook { height:100%; display:flex; flex-direction:column; justify-content:center; }
@@ .hook-value { font-size:6.4em; text-shadow:none; font-family:var(--hf); }
@@ .hook-label { font-family:var(--bf); font-size:1.1em; letter-spacing:.02em; }
@@ .hook-punch { font-size:1.7em; max-width:32ch; }
@@ .bars { height:100%; max-width:none; gap:.8em; justify-content:space-evenly; }
@@ .bar-label { font-size:1.35em; }
@@ .bar-note { font-family:var(--bf); font-size:1em; }
@@ .bar-track { height:1em; }
@@ .matrix { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); grid-auto-rows:auto; gap:.8em; height:auto; width:100%; align-content:center; }
@@ .body > .matrix, @@ .body > .compare, @@ .body > .steps, @@ .body > .bars, @@ .body > .hub, @@ .body > .quote { height:auto; align-self:center; }
@@ .mx-card { display:flex; flex-direction:column; justify-content:center; padding:1em 1.15em; min-height:6.2em; }
@@ .mx-label { font-size:1.65em; font-weight:var(--hw, 700); font-family:var(--hf); color:var(--ink); }
@@ .mx-detail { display:block; font-size:1.2em; line-height:1.4; color:var(--muted); margin-top:.35em; -webkit-line-clamp:4; }
@@ .flow-node { padding:.8em 1em; }
@@ .body > .flow, @@ .body > .transform { height:auto; align-self:center; }
@@ .flow { height:auto; align-items:center; justify-content:center; }
@@ .flow-horizontal .flow-node { flex:1 1 12em; align-self:center; min-height:0; max-width:18em; }
@@ .flow-body { display:flex; flex-direction:column; gap:.35em; width:100%; }
@@ .flow-label, @@ .flow-sub { display:block; }
@@ .flow-label { font-size:1.7em; font-weight:700; }
@@ .flow-sub { font-size:1.15em; line-height:1.35; }
@@ .flow-node { min-width:10em; padding:1em 1.1em; }
@@ .transform { height:auto; margin-top:.6em; }
@@ .tr-stage { width:100%; align-items:center; }
@@ .tr-src, @@ .tr-dest { align-self:center; }
@@ .hub { height:100%; justify-content:center; }
@@ .hub-center-label { font-size:1.5em; }
@@ .hub-center-sub { font-family:var(--bf); font-size:.8em; }
@@ .hub-label { font-size:1em; -webkit-line-clamp:3; }
@@ .hub-sub { font-family:var(--bf); font-size:.8em; }
@@ .hub-card { max-width:11em; padding:.6em .8em; }
@@ .panel-body .pl { font-size:1.05em; }
@@ .device { border-radius:.8em; }
@@ .diagram { min-height:12em; max-height:none; }
@@ .eq { padding:.6em 1em; }
@@ .paper-img { max-height:min(640px, 64vh); width:auto; object-fit:contain; }
@@ .reveal.text, @@ .text .bullets { height:100%; }

/* ---------- cover / opening slide (all families) ---------- */
@@ .scene.is-hero { display:flex; flex-direction:column; justify-content:center; }
@@ .scene.is-hero h2 { font-size:4.5em; line-height:1.0; max-width:92%; margin:0 0 .45em; }
@@ .scene.is-hero .body { flex:0 0 auto; height:auto; display:block; }
@@ .scene.is-hero .body > * { height:auto; }
@@ .scene.is-hero .bullets, @@ .scene.is-hero .v-chips { display:flex; flex-wrap:wrap; gap:.55em; height:auto; max-width:none; }
@@ .scene.is-hero .bullets li, @@ .scene.is-hero .v-chip { flex:0 0 auto; width:auto; padding:.3em 1em; border-radius:999px; }
@@ .scene.is-hero .b-text { font-size:1em; }
@@ .scene.is-hero .b-mark { display:none; }
@@ .scene.is-hero .v-spot { height:auto; }
@@ .scene.is-hero .v-lead { font-size:1.5em; font-weight:var(--bw, 500); font-family:var(--bf); color:var(--muted); }
@@ .scene.is-hero .v-cards, @@ .scene.is-hero .v-bento, @@ .scene.is-hero .v-notes { display:none; }

/* Never split a word mid-way: the fitter shrinks type instead. */
@@ .scene h2, @@ .scene .body * { overflow-wrap:normal; word-break:normal; hyphens:none; }

/* ---------- subtitle: small and quiet ---------- */
@@ .caption {
  display:flex; opacity:1; left:50%; right:auto; transform:translateX(-50%); bottom:26px;
  width:auto; height:auto; min-height:0; max-height:none; max-width:min(1240px, calc(100% - 300px)); padding:.4em 1.2em; border:0; border-radius:999px;
  background:color-mix(in srgb, var(--ink) 74%, transparent); box-shadow:none; backdrop-filter:blur(6px);
}
@@ .cap-text {
  font-family:var(--bf); font-size:20px; line-height:1.35; font-weight:500; color:var(--bg); text-shadow:none;
  text-transform:none; letter-spacing:0; display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden; -webkit-line-clamp:2; max-width:none; min-height:0; text-align:center; margin:0;
}
@@ .cap-ticks, @@ .cap-tag { display:none; }

/* ============================ FAMILY: split ============================ */
@@[data-edu="split"] { --r:0; --bd:0; --sh:none; --cardbg:transparent; }
@@[data-edu="split"] .slide .bg::before { opacity:1; content:""; inset:0 auto 0 0; width:36%; height:auto; background:color-mix(in srgb, var(--a) 10%, var(--bg)); background-image:none; -webkit-mask-image:none; mask-image:none; }
@@[data-edu="split"] .slide[data-alt="1"] .bg::before { inset:0 0 0 auto; }
@@[data-edu="split"] .slide[data-alt="2"] .bg::before { inset:0 0 auto 0; width:100%; height:31%; }
@@[data-edu="split"] .slide[data-index="0"] .bg::before { opacity:0; }
@@[data-edu="split"] .scene:not(.is-hero) { display:grid; grid-template-columns:27% minmax(0,1fr); grid-template-rows:minmax(0,1fr); column-gap:4.4em; }
@@[data-edu="split"] .slide[data-alt="1"] .scene:not(.is-hero) { grid-template-columns:minmax(0,1fr) 27%; }
@@[data-edu="split"] .slide[data-alt="2"] .scene:not(.is-hero) { grid-template-columns:minmax(0,1fr); grid-template-rows:auto minmax(0,1fr); }
@@[data-edu="split"] .scene:not(.is-hero) h2 { grid-column:1; grid-row:1; align-self:center; font-size:2.3em; margin:0; }
@@[data-edu="split"] .slide[data-alt="1"] .scene:not(.is-hero) h2 { grid-column:2; }
@@[data-edu="split"] .scene:not(.is-hero) h2::before { content:""; display:block; width:2.4em; height:.26em; margin-bottom:.55em; border-radius:1em; background:var(--a); }
@@[data-edu="split"] .slide[data-alt="2"] .scene:not(.is-hero) h2 { grid-row:1; align-self:end; margin-bottom:.9em; font-size:2.4em; }
@@[data-edu="split"] .scene:not(.is-hero) .body { grid-column:2; grid-row:1; }
@@[data-edu="split"] .slide[data-alt="1"] .scene:not(.is-hero) .body { grid-column:1; }
@@[data-edu="split"] .slide[data-alt="2"] .scene:not(.is-hero) .body { grid-column:1; grid-row:2; }
@@[data-edu="split"] .bullets li, @@[data-edu="split"] .v-rail li, @@[data-edu="split"] .v-agenda li, @@[data-edu="split"] .v-col li, @@[data-edu="split"] .steps .step { border-bottom:1px solid var(--line); padding-left:0; }
@@[data-edu="split"] .bullets li:last-child, @@[data-edu="split"] .steps .step:last-child { border-bottom:0; }
@@[data-edu="split"] .v-card, @@[data-edu="split"] .v-tile { border-top:.2em solid var(--a); background:color-mix(in srgb, var(--a) 6%, var(--bg)); padding-top:.7em; }
@@[data-edu="split"] .cmp-col, @@[data-edu="split"] .stat-card, @@[data-edu="split"] .mx-card { background:color-mix(in srgb, var(--a) 7%, var(--bg)); border-radius:.3em; }
@@[data-edu="split"] .stat-card { border-left:.28em solid var(--a); }
@@[data-edu="split"] .b-mark { width:.45em; height:.45em; border-radius:50%; }
@@[data-edu="split"] .decos { display:block; }
@@[data-edu="split"] .deco { stroke-width:2.5; opacity:.55; }

/* ============================ FAMILY: band ============================ */
@@[data-edu="band"] { --r:.8em; --bd:0; --sh:0 .2em .7em rgba(0,0,0,.09); --cardbg:var(--panel); }
@@[data-edu="band"] .slide .bg::before { opacity:1; content:""; inset:0; background-image:repeating-linear-gradient(135deg, transparent 0 22px, color-mix(in srgb, var(--a) 7%, transparent) 22px 24px); -webkit-mask-image:none; mask-image:none; }
@@[data-edu="band"] .slide .bg::after { opacity:.14; width:760px; height:760px; right:-240px; bottom:-340px; top:auto; filter:blur(50px); }
@@[data-edu="band"] h2 { align-self:stretch; font-size:2.15em; padding:.32em .8em; margin:0 0 .7em; background:color-mix(in srgb, var(--a) 15%, var(--bg)); border-left:.3em solid var(--a); border-radius:0 .6em .6em 0; }
@@[data-edu="band"] .slide[data-alt="1"] h2 { background:var(--a); color:var(--bg); border-left:0; border-radius:.5em; }
@@[data-edu="band"] .slide[data-alt="1"] h2 .accent { color:var(--bg); text-decoration:underline; text-decoration-thickness:.07em; text-underline-offset:.12em; }
@@[data-edu="band"] .slide[data-alt="2"] h2 { background:none; border-left:0; border-bottom:.12em solid var(--a); border-radius:0; padding-left:0; }
@@[data-edu="band"] .bullets li, @@[data-edu="band"] .v-card, @@[data-edu="band"] .v-tile, @@[data-edu="band"] .steps .step, @@[data-edu="band"] .mx-card, @@[data-edu="band"] .stat-card, @@[data-edu="band"] .cmp-col { border-top:.28em solid var(--a); }
@@[data-edu="band"] .bullets li:nth-child(even), @@[data-edu="band"] .v-card:nth-child(even), @@[data-edu="band"] .v-tile:nth-child(even), @@[data-edu="band"] .steps .step:nth-child(even), @@[data-edu="band"] .mx-card:nth-child(even) { border-top-color:var(--b); }
@@[data-edu="band"] .v-rail li, @@[data-edu="band"] .v-agenda li, @@[data-edu="band"] .v-col li { border-top:0; border-left:.28em solid var(--a); }
@@[data-edu="band"] .bullets.grid { grid-template-columns:repeat(2, minmax(0,1fr)); }

/* ============================ FAMILY: sketch ============================ */
@@[data-edu="sketch"] { --r:.9em; --bd:0; --sh:none; --cardbg:color-mix(in srgb, var(--panel) 55%, var(--bg)); }
@@[data-edu="sketch"] .slide .bg::before { opacity:1; content:""; inset:0; background-image:radial-gradient(color-mix(in srgb, var(--ink) 20%, transparent) 1.6px, transparent 1.9px); background-size:34px 34px; -webkit-mask-image:none; mask-image:none; }
@@[data-edu="sketch"] h2 { font-size:3.3em; line-height:.98; margin-bottom:.1em; }
@@[data-edu="sketch"] h2 .accent { color:var(--ink); background:linear-gradient(transparent 58%, color-mix(in srgb, var(--a) 38%, transparent) 58% 94%, transparent 94%) no-repeat 0 0; background-size:calc(var(--p, 1) * 100%) 100%; padding:0 .1em; }
@@[data-edu="sketch"] .h-under, @@[data-edu="notebook"] .h-under { display:block; width:min(62%, 9em); height:.42em; margin:0 0 .55em; overflow:visible; flex:none; }
@@[data-edu="sketch"] .h-under path, @@[data-edu="notebook"] .h-under path { fill:none; stroke:var(--a); stroke-width:5; stroke-linecap:round; stroke-dasharray:1; stroke-dashoffset:calc(1 - var(--p, 1)); vector-effect:non-scaling-stroke; }
@@[data-edu="sketch"] .bullets li::before, @@[data-edu="sketch"] .v-card::before, @@[data-edu="sketch"] .v-tile::before, @@[data-edu="sketch"] .steps .step::before, @@[data-edu="sketch"] .cmp-col::before, @@[data-edu="sketch"] .stat-card::before, @@[data-edu="sketch"] .mx-card::before, @@[data-edu="sketch"] .v-rail li::before, @@[data-edu="sketch"] .v-agenda li::before, @@[data-edu="sketch"] .v-col li::before {
  content:""; position:absolute; inset:0; pointer-events:none; border:.1em solid color-mix(in srgb, var(--ink) 85%, transparent);
  border-radius:255px 14px 225px 14px / 14px 225px 14px 255px;
}
@@[data-edu="sketch"] .v-note::before { display:none; }
@@[data-edu="sketch"] .bullets li:nth-child(odd), @@[data-edu="sketch"] .steps .step:nth-child(odd), @@[data-edu="sketch"] .v-tile:nth-child(odd) { rotate:-.5deg; }
@@[data-edu="sketch"] .bullets li:nth-child(even), @@[data-edu="sketch"] .steps .step:nth-child(even), @@[data-edu="sketch"] .v-tile:nth-child(even) { rotate:.45deg; }
@@[data-edu="sketch"] .b-mark { width:.5em; height:.5em; border-radius:50% 40% 55% 45%; background:var(--a); }
@@[data-edu="sketch"] .step-num, @@[data-edu="sketch"] .v-idx, @@[data-edu="sketch"] .v-num, @@[data-edu="sketch"] .v-dot { border-radius:50% 42% 54% 46%; }
@@[data-edu="sketch"] .decos, @@[data-edu="notebook"] .decos { display:block; position:absolute; inset:0; pointer-events:none; z-index:0; }
@@[data-edu="sketch"] .b-text, @@[data-edu="sketch"] .v-t, @@[data-edu="sketch"] .step-text { font-size:1.4em; }

/* ============================ FAMILY: poster ============================ */
@@[data-edu="poster"] { --r:.2em; --bd:0; --sh:.28em .28em 0 var(--a); --cardbg:var(--ink); }
@@[data-edu="poster"] .slide .bg::before { opacity:.16; content:""; inset:0 0 auto 0; height:34%; width:100%; background:var(--a); background-image:none; -webkit-mask-image:none; mask-image:none; }
@@[data-edu="poster"] .slide[data-alt="1"] .bg::before { inset:0 auto 0 0; width:22%; height:100%; }
@@[data-edu="poster"] .slide[data-alt="2"] .bg::before { inset:auto 0 0 0; height:30%; width:100%; }
@@[data-edu="poster"] h2 { font-size:4em; line-height:.94; text-transform:uppercase; letter-spacing:-.005em; margin-bottom:.4em; }
@@[data-edu="poster"] .slide[data-alt="1"] .stage-wrap { padding-left:calc(22% + 40px); }
@@[data-edu="poster"].vertical h2 { font-size:2.7em; overflow-wrap:normal; word-break:normal; hyphens:none; }
@@[data-edu="poster"].vertical .scene.is-hero h2 { font-size:3em; }
@@[data-edu="poster"] .b-text, @@[data-edu="poster"] .v-t, @@[data-edu="poster"] .step-text, @@[data-edu="poster"] .cmp-title, @@[data-edu="poster"] .cmp-col li, @@[data-edu="poster"] .mx-label, @@[data-edu="poster"] .stat-label, @@[data-edu="poster"] .flow-label, @@[data-edu="poster"] .hub-label { color:var(--bg); }
@@[data-edu="poster"] .mx-detail { color:color-mix(in srgb, var(--bg) 70%, transparent); }
@@[data-edu="poster"] .v-chip { background:var(--ink); color:var(--bg); border:0; }
@@[data-edu="poster"] .v-note .v-t { color:#1f1f1f; }
@@[data-edu="poster"] .v-idx, @@[data-edu="poster"] .v-num, @@[data-edu="poster"] .v-k, @@[data-edu="poster"] .v-dot, @@[data-edu="poster"] .step-num { background:var(--a); color:var(--ink); }
@@[data-edu="poster"] .bullets li:nth-child(even), @@[data-edu="poster"] .steps .step:nth-child(even) { box-shadow:.28em .28em 0 var(--b); }
@@[data-edu="poster"] .stat-value { font-size:4.4em; }
@@[data-edu="poster"] .decos { display:block; position:absolute; inset:0; pointer-events:none; z-index:0; }
@@[data-edu="poster"] .deco { stroke-width:6; }
@@[data-edu="poster"] .quote p, @@[data-edu="poster"] .v-lead { text-transform:uppercase; }

/* ============================ FAMILY: bento ============================ */
@@[data-edu="bento"] { --r:1.1em; --bd:0; --sh:none; --cardbg:color-mix(in srgb, var(--a) 13%, var(--bg)); }
@@[data-edu="bento"] .slide .bg { background:color-mix(in srgb, var(--ink) 4%, var(--bg)); }
@@[data-edu="bento"] h2 { font-size:1.95em; margin-bottom:.6em; }
@@[data-edu="bento"] .slide[data-alt="1"] h2 { text-align:right; align-self:flex-end; }
@@[data-edu="bento"] .slide[data-alt="2"] .scene:not(.is-hero) { flex-direction:column-reverse; }
@@[data-edu="bento"] .slide[data-alt="2"] h2 { margin:.6em 0 0; font-size:1.7em; }
@@[data-edu="bento"] .bullets, @@[data-edu="bento"] .v-bento { grid-template-columns:repeat(4, minmax(0,1fr)); gap:.6em; }
@@[data-edu="bento"] .bullets.grid { grid-template-columns:repeat(4, minmax(0,1fr)); }
@@[data-edu="bento"] .bullets li:first-child, @@[data-edu="bento"] .v-bento .v-tile:first-child { grid-column:span 2; grid-row:span 2; background:var(--ink); }
@@[data-edu="bento"] .bullets li:first-child .b-text, @@[data-edu="bento"] .v-bento .v-tile:first-child .v-t { color:var(--bg); font-size:1.7em; }
@@[data-edu="bento"] .bullets li:first-child:nth-last-child(2), @@[data-edu="bento"] .bullets li:first-child:nth-last-child(2) ~ li { grid-column:span 2; grid-row:span 2; }
@@[data-edu="bento"] .bullets li:first-child:nth-last-child(3) ~ li { grid-column:span 2; }
@@[data-edu="bento"] .bullets li:first-child:nth-last-child(4) + li { grid-column:span 2; }
@@[data-edu="bento"] .v-bento .v-tile:first-child:nth-last-child(3) ~ .v-tile { grid-column:span 2; }
@@[data-edu="bento"] .v-bento .v-tile:first-child:nth-last-child(4) + .v-tile { grid-column:span 2; }
@@[data-edu="bento"] .bullets li:nth-child(3n+2), @@[data-edu="bento"] .v-card:nth-child(3n+2), @@[data-edu="bento"] .v-tile:nth-child(3n+2), @@[data-edu="bento"] .steps .step:nth-child(3n+2) { background:color-mix(in srgb, var(--b) 15%, var(--bg)); }
@@[data-edu="bento"] .bullets li:nth-child(3n), @@[data-edu="bento"] .v-card:nth-child(3n), @@[data-edu="bento"] .v-tile:nth-child(3n), @@[data-edu="bento"] .steps .step:nth-child(3n) { background:var(--panel); }
@@[data-edu="bento"] .bullets li { align-items:flex-start; flex-direction:column; justify-content:flex-end; padding:.8em 1em; }
@@[data-edu="bento"] .b-mark { width:1em; height:.28em; border-radius:1em; }

/* ============================ FAMILY: notebook ============================ */
@@[data-edu="notebook"] { --r:.3em; --bd:0; --sh:none; --cardbg:transparent; }
@@[data-edu="notebook"] .slide .bg { background:color-mix(in srgb, var(--panel) 45%, var(--bg)); }
@@[data-edu="notebook"] .slide .bg::before { opacity:1; content:""; inset:0; background-image:linear-gradient(90deg, transparent 146px, color-mix(in srgb, #e11d48 60%, transparent) 146px 149px, transparent 149px), repeating-linear-gradient(transparent 0 41px, color-mix(in srgb, var(--a) 24%, transparent) 41px 43px); -webkit-mask-image:none; mask-image:none; }
@@[data-edu="notebook"] .stage-wrap { padding-left:200px; }
@@[data-edu="notebook"] h2 { font-size:2.8em; line-height:1.02; margin-bottom:.1em; }
@@[data-edu="notebook"] h2 .accent { color:var(--ink); background:linear-gradient(transparent 55%, color-mix(in srgb, #facc15 70%, transparent) 55% 92%, transparent 92%) no-repeat 0 0; background-size:calc(var(--p, 1) * 100%) 100%; padding:0 .12em; }
@@[data-edu="notebook"] .bullets li, @@[data-edu="notebook"] .steps .step, @@[data-edu="notebook"] .v-rail li, @@[data-edu="notebook"] .v-agenda li, @@[data-edu="notebook"] .v-col li { border-bottom:.08em dashed color-mix(in srgb, var(--ink) 35%, transparent); padding-left:.2em; }
@@[data-edu="notebook"] .b-mark { width:.8em; height:.8em; border-radius:.2em .3em .15em .3em; background:transparent; border:.12em solid var(--a); }
@@[data-edu="notebook"] .b-text, @@[data-edu="notebook"] .v-t, @@[data-edu="notebook"] .step-text { font-size:1.4em; }
@@[data-edu="notebook"] .v-card, @@[data-edu="notebook"] .v-tile { background:color-mix(in srgb, var(--bg) 70%, transparent); border-left:.14em solid var(--a); }
@@[data-edu="notebook"] .cmp-col, @@[data-edu="notebook"] .stat-card, @@[data-edu="notebook"] .mx-card { background:color-mix(in srgb, var(--bg) 78%, transparent); border:.08em solid color-mix(in srgb, var(--ink) 30%, transparent); }
@@[data-edu="notebook"] .step-num, @@[data-edu="notebook"] .v-idx, @@[data-edu="notebook"] .v-num { border-radius:50% 44% 56% 46%; }
@@[data-edu="notebook"] .slide[data-index="0"] .stage-wrap { padding-left:200px; }

/* ---------- cover art: fills the empty half of the opening slide ---------- */
@@ .slide .cover-art {
  position:absolute; z-index:0; right:-7%; top:50%; width:50%; aspect-ratio:1; translate:0 -50%; border-radius:50%; pointer-events:none;
  background:radial-gradient(circle at 34% 34%, color-mix(in srgb, var(--a) 38%, transparent), color-mix(in srgb, var(--b) 20%, transparent) 58%, transparent 71%);
  scale:calc(1 + sin(var(--tt, 0) * .8) * .03);
}
@@[data-edu="sketch"] .slide .cover-art { background:none; border:.35vw dashed color-mix(in srgb, var(--a) 45%, transparent); width:22%; right:6%; rotate:calc(var(--tt, 0) * 4deg); }
@@ .slide:has(.paper) .cover-art { display:none; }
@@ .scene.is-hero .body.cover-body { display:grid; grid-template-columns:minmax(0,1.1fr) minmax(220px, 460px); gap:28px; align-items:center; }
@@ .paper.is-cover .paper-img { width:100%; max-width:460px; max-height:min(640px, 64vh); object-fit:contain; border-radius:12px; box-shadow:0 18px 48px rgba(15,23,42,.16); }
@@[data-edu="poster"] .slide .cover-art { border-radius:4%; width:24%; right:4%; top:64%; background:var(--a); opacity:.9; rotate:calc(8deg + sin(var(--tt, 0)) * 3deg); box-shadow:-1.4vw 1.4vw 0 var(--b); }
@@[data-edu="band"] .slide .cover-art { border-radius:0; width:34%; right:0; top:0; height:100%; aspect-ratio:auto; translate:none; background:repeating-linear-gradient(135deg, color-mix(in srgb, var(--a) 22%, transparent) 0 3px, transparent 3px 22px); }
@@[data-edu="notebook"] .slide .cover-art { display:none; }
@@.vertical .slide .cover-art { width:90%; right:-30%; top:auto; bottom:-8%; translate:none; }

/* ---------- doodles (sketch / notebook / poster / split) ---------- */
@@ .deco { position:absolute; width:78px; height:78px; fill:none; stroke:var(--a); stroke-width:4.5; stroke-linecap:round; stroke-linejoin:round; overflow:visible; vector-effect:non-scaling-stroke; }
@@ .deco path { fill:none; stroke:var(--a); stroke-dasharray:1; stroke-dashoffset:calc(1 - var(--p, 1)); vector-effect:non-scaling-stroke; }
@@ .deco.d1 { top:10px; left:46%; rotate:calc(sin(var(--tt, 0) * 1.3) * 7deg); }
@@ .deco.d2 { right:10px; bottom:96px; rotate:calc(cos(var(--tt, 0) * 1.1) * 6deg); }
@@ .deco.d3 { left:18px; bottom:118px; width:66px; height:66px; stroke:var(--b); rotate:calc(sin(var(--tt, 0) * .9 + 1) * 8deg); }
@@ .deco.d3 path { stroke:var(--b); }
@@ .slide[data-alt="1"] .deco.d1 { left:auto; right:30%; }
@@ .slide[data-alt="2"] .deco.d2 { bottom:auto; top:120px; right:12px; }
body.capture.edu .slide.active .deco, body.capture.edu .slide.active .deco path, body.capture.edu .slide.active .h-under path, body.capture.edu .slide.active .v-line path, body.capture.edu .slide.active h2 .accent { animation:none; }

/* ---------- focus (the item being explained right now) ---------- */
@@ .bullets li.is-active, @@ .v-card.is-active, @@ .v-tile.is-active, @@ .steps .step.is-active, @@ .stat-card.is-active, @@ .cmp-col.is-active, @@ .mx-card.is-active { transform:translateY(-.12em) scale(1.02); box-shadow:0 0 0 .12em var(--a), 0 .5em 1.4em color-mix(in srgb, var(--a) 30%, transparent); z-index:3; }
@@ .v-note.is-active { box-shadow:0 0 0 .12em var(--a), .12em .3em .8em rgba(0,0,0,.3); }

/* ---------- vertical (9:16) ---------- */
@@.vertical .scene { font-size:calc(var(--fit, 1) * 30px); }
@@.vertical .stage-wrap { padding:120px 64px 210px; }
@@.vertical .brand-tag { right:64px; top:50px; font-size:24px; }
@@.vertical h2 { font-size:2.5em; }
@@.vertical .scene.is-hero h2 { font-size:3.6em; }
@@.vertical .bullets.grid, @@.vertical .v-split, @@.vertical .v-cards, @@.vertical .compare { grid-template-columns:minmax(0,1fr); }
@@.vertical .body.two { grid-template-columns:minmax(0,1fr); }
@@.vertical .v-stairs { grid-template-columns:minmax(0,1fr); align-items:stretch; }
@@.vertical .v-st { height:auto; }
@@.vertical .cmp-vs { display:none; }
@@.vertical .caption { bottom:96px; max-width:calc(100% - 128px); }
@@.vertical .cap-text { font-size:28px; -webkit-line-clamp:3; }
@@[data-edu="split"].vertical .scene:not(.is-hero), @@[data-edu="split"].vertical .slide[data-alt="1"] .scene:not(.is-hero) { grid-template-columns:minmax(0,1fr); grid-template-rows:auto minmax(0,1fr); }
@@[data-edu="split"].vertical .scene:not(.is-hero) h2, @@[data-edu="split"].vertical .slide[data-alt="1"] .scene:not(.is-hero) h2 { grid-column:1; grid-row:1; margin-bottom:.8em; }
@@[data-edu="split"].vertical .scene:not(.is-hero) .body, @@[data-edu="split"].vertical .slide[data-alt="1"] .scene:not(.is-hero) .body { grid-column:1; grid-row:2; }
@@[data-edu="split"].vertical .slide .bg::before, @@[data-edu="split"].vertical .slide[data-alt="1"] .bg::before { inset:0 0 auto 0; width:100%; height:24%; }
@@[data-edu="bento"].vertical .bullets, @@[data-edu="bento"].vertical .v-bento { grid-template-columns:repeat(2, minmax(0,1fr)); }
@@[data-edu="notebook"].vertical .stage-wrap { padding-left:120px; }
@@[data-edu="poster"].vertical .slide[data-alt="1"] .stage-wrap { padding-left:64px; }
@@[data-edu="poster"].vertical .slide[data-alt="1"] .bg::before { inset:0 0 auto 0; width:100%; height:24%; }

/* ---------- square (1:1) ---------- */
@media (aspect-ratio:1/1) {
  @@.vertical .scene { font-size:calc(var(--fit, 1) * 24px); }
  @@.vertical .stage-wrap { padding:90px 56px 130px; }
  @@.vertical .caption { bottom:34px; }
  @@.vertical .cap-text { font-size:22px; -webkit-line-clamp:2; }
}
"""

_KEYFRAMES = r"""
@property --p { syntax:'<number>'; inherits:true; initial-value:1; }
@keyframes drawp { from { --p:0; } to { --p:1; } }
html body.edu:not(.capture) .slide.active .deco,
html body.edu:not(.capture) .slide.active .deco path,
html body.edu:not(.capture) .slide.active .h-under path,
html body.edu:not(.capture) .slide.active .v-line path,
html body.edu:not(.capture) .slide.active h2 .accent { animation:drawp .9s cubic-bezier(.4,0,.2,1) .25s both; }
/* Frame capture seeks then screenshots: wall-clock transitions would be caught mid-flight. */
@@.capture .slide *, @@.capture .slide *::before, @@.capture .slide *::after { transition:none !important; }
html body.edu.measuring.measuring.measuring.measuring.measuring.measuring.measuring.measuring *, html body.edu.measuring.measuring.measuring.measuring.measuring.measuring.measuring.measuring *::before, html body.edu.measuring.measuring.measuring.measuring.measuring.measuring.measuring.measuring *::after { animation:none !important; transition:none !important; transform:none !important; rotate:none !important; translate:none !important; scale:none !important; }
"""


def _important(css: str, prefix: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = css.replace("@@", prefix)

    def bang(m: re.Match) -> str:
        prop, val, end = m.group(1), m.group(2), m.group(3)
        if "!important" in val or prop.strip().startswith("@"):
            return m.group(0)
        return f"{prop}:{val.rstrip()} !important{end}"

    return re.sub(r"([\w-]+)\s*:([^{};]+?)(;|(?=\}))", bang, css)


EDU_CSS = (
    "\n/* ===== design families ===== */\n"
    + _important(_font_css(), "")
    + "\n"
    + _important(_RAW + _extra_css(), _P)
    + "\n"
    + _KEYFRAMES.replace("@@", _P)
)

# Grow-or-shrink to fit. Picks the largest --fit (0.5 .. FIT_MAX) at which the
# slide's content still fits, so short slides fill the frame with bigger type and
# long ones scale down instead of clipping.
EDU_FIT_JS = r"""
  async function eduFit(slide) {
    if (!slide) return;
    try {
      if (document.fonts && document.fonts.ready) {
        await Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 2500))]);
      }
    } catch (e) { /* best-effort */ }
    const scene = slide.querySelector('.scene');
    const body = slide.querySelector('.body');
    if (!scene || !body) return;
    const hero = scene.classList.contains('is-hero');
    const FIT_MAX = hero ? 1.6 : 2.3;
    document.body.classList.add('measuring');
    // Inner boxes can overflow themselves while still sitting inside the body, so
    // check every block-level descendant, not only the outer containers.
    const head = slide.querySelector('h2');
    const inner = [...(head ? [head] : []), ...body.querySelectorAll('*')].filter((e) => {
      const d = getComputedStyle(e).display;
      return d !== 'inline' && d !== 'contents' && !(e instanceof SVGElement);
    });
    // Handwriting fonts have tall ascenders/descenders that spill a few px; allow a
    // fraction of the line height before calling it overflow.
    const overInner = () => inner.some((e) => {
      const slack = Math.max(4, (parseFloat(getComputedStyle(e).fontSize) || 16) * 0.3);
      return e.scrollHeight > e.clientHeight + slack || e.scrollWidth > e.clientWidth + slack;
    });
    const over = () => overInner() ||
      body.scrollHeight > body.clientHeight + 4 || body.scrollWidth > body.clientWidth + 4 ||
      scene.scrollHeight > scene.clientHeight + 8 || scene.scrollWidth > scene.clientWidth + 8;
    scene.style.setProperty('--fit', String(FIT_MAX));
    let best = FIT_MAX;
    if (over()) {
      let lo = 0.45, hi = FIT_MAX;
      for (let i = 0; i < 9; i++) {
        const mid = (lo + hi) / 2;
        scene.style.setProperty('--fit', mid.toFixed(3));
        if (over()) hi = mid; else lo = mid;
      }
      best = lo;
    }
    scene.style.setProperty('--fit', best.toFixed(3));
    document.body.classList.remove('measuring');
  }
"""


def font_pair(style_key: str) -> tuple[str, str]:
    """(heading font, body font) the renderer uses for this style."""
    fam, var = edu_family(style_key)
    hf, _hw, bf = _FONTS[fam][var]
    return hf, bf
