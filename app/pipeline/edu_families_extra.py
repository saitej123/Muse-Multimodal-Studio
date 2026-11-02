"""Six more design families for the slide HTML (chalk, terminal, pop, cinema,
glass, magazine).

Same contract as the first six in ``edu_theme``: they change structure and
motion, not just colour. Colours still come from the chosen theme
(``--ink --bg --panel --a --b``); one unit is ``1em`` so the fitter can scale.

CSS is plain (no ``url(...)``, no ``;`` inside values) because
``edu_theme._important`` post-processes it with a regex. ``@@`` is the
placeholder for ``html body.edu``.
"""
from __future__ import annotations

EXTRA_FAMILIES = ("chalk", "terminal", "pop", "cinema", "glass", "magazine")

EXTRA_FAMILY_MAP = {
    "chalk": ("teardown", "chalk", "formula_board", "lab_notes", "worked_example", "hint_ladder",
              "misconception", "exam_prompt", "socratic_q"),
    "terminal": ("terminal", "blueprint", "cli_prompt", "code_diff", "hf_code_ed", "changelog_log",
                 "err_trace", "api_card", "typewriter_line"),
    "pop": ("playful", "kinetic", "caption_pop", "rainbow_bar", "word_slam", "promo_sprint",
            "bumper_ident", "sports_lower", "hf_creative"),
    "cinema": ("cinematic", "documentary", "cold_open", "quote_fullbleed", "end_card", "credits_roll",
               "freeze_frame", "flashback", "title_safe"),
    "glass": ("glass", "saas", "modern", "device", "pip_overlay", "gamma", "soft_signal",
              "hf_product_launch", "logo_intro"),
    "magazine": ("quote_pull", "big_stat", "pricing_tiers", "glossary_term", "recap_list", "north_star",
                 "okr_cards", "chapter_card", "ticker_news"),
}

EXTRA_FAMILY_INFO = {
    "chalk": {
        "label": "Chalkboard",
        "blurb": "Chalk-dust board with a frame, dashed chalk outlines and star bullets. Titles are written in, cards swing in like chalk notes.",
        "uses": "Lessons, worked examples, revision",
        "flagship": "teardown",
    },
    "terminal": {
        "label": "Terminal",
        "blurb": "Monospace with a $ prompt, a blinking cursor and window-style cards. Lines type in from the left.",
        "uses": "Code, APIs, engineering, dev content",
        "flagship": "terminal",
    },
    "pop": {
        "label": "Pop",
        "blurb": "Comic energy: halftone dots, thick ink outlines, hard shadows and stamp-in titles that grab attention.",
        "uses": "Shorts, hooks, kids and campus content",
        "flagship": "playful",
    },
    "cinema": {
        "label": "Cinema",
        "blurb": "Letterbox bars, a vignette and slow push-in titles. Content sits in lower-third style strips.",
        "uses": "Stories, trailers, documentary-style videos",
        "flagship": "cinematic",
    },
    "glass": {
        "label": "Glass",
        "blurb": "A glowing gradient mesh with frosted glass cards that flip in and a gently pulsing orb.",
        "uses": "SaaS, product, modern keynote",
        "flagship": "glass",
    },
    "magazine": {
        "label": "Magazine",
        "blurb": "Big outlined numerals, a column rule, hard section lines and an oversized headline. Sections count themselves in.",
        "uses": "Listicles, rankings, key takeaways",
        "flagship": "big_stat",
    },
}

# (heading font, heading weight, body font), four per family
EXTRA_FONTS = {
    "chalk": [("Gloria Hallelujah", 400, "Patrick Hand"), ("Kalam", 700, "Kalam"),
              ("Permanent Marker", 400, "Patrick Hand"), ("Caveat", 700, "Kalam")],
    "terminal": [("JetBrains Mono", 700, "IBM Plex Mono"), ("Space Mono", 700, "Space Mono"),
                 ("IBM Plex Mono", 600, "JetBrains Mono"), ("JetBrains Mono", 800, "Space Mono")],
    "pop": [("Bangers", 400, "Nunito"), ("Fredoka", 700, "Fredoka"),
            ("Baloo 2", 800, "Nunito"), ("Rubik", 800, "Rubik")],
    "cinema": [("Playfair Display", 700, "Inter"), ("Lora", 700, "Work Sans"),
               ("Fraunces", 600, "DM Sans"), ("Newsreader", 600, "Figtree")],
    "glass": [("Plus Jakarta Sans", 800, "Inter"), ("Outfit", 700, "DM Sans"),
              ("Sora", 700, "Manrope"), ("Manrope", 800, "Figtree")],
    "magazine": [("Playfair Display", 800, "Work Sans"), ("Oswald", 700, "Barlow"),
                 ("Bricolage Grotesque", 800, "DM Sans"), ("Fraunces", 800, "Inter")],
}
EXTRA_BODY_WEIGHT = {"chalk": 400, "terminal": 400, "pop": 600}

# Google Fonts the new families need (appended to the <link> in content.py).
EXTRA_FONT_QUERY = "&family=Bangers&family=Lora:wght@500;700"

_CARD_CLASSES = (".bullets li", ".v-card", ".v-tile", ".steps .step", ".cmp-col", ".stat-card",
                 ".mx-card", ".v-rail li", ".v-agenda li", ".v-col li")


def _cards(fam: str, tail: str = "") -> str:
    return ", ".join(f'@@[data-edu="{fam}"] {c}{tail}' for c in _CARD_CLASSES)


_CHALK = r"""
/* ============================ FAMILY: chalk ============================ */
@@[data-edu="chalk"] { --r:.5em; --bd:.09em; --sh:none; --cardbg:transparent; }
@@[data-edu="chalk"] .slide .bg { background:radial-gradient(120% 90% at 20% 10%, color-mix(in srgb, var(--bg) 86%, var(--a)) 0%, var(--bg) 70%); }
@@[data-edu="chalk"] .slide .bg::before { opacity:1; content:""; inset:0; background-image:radial-gradient(color-mix(in srgb, var(--ink) 9%, transparent) 1.2px, transparent 1.7px), radial-gradient(color-mix(in srgb, var(--ink) 6%, transparent) 2px, transparent 2.8px); background-size:23px 23px, 61px 61px; background-position:0 0, 11px 17px; -webkit-mask-image:none; mask-image:none; }
@@[data-edu="chalk"] .slide .bg::after { opacity:1; content:""; inset:0; width:auto; height:auto; filter:none; border-radius:0; background:none; box-shadow:inset 0 0 0 .55vw color-mix(in srgb, var(--ink) 16%, transparent), inset 0 0 180px rgba(0,0,0,.22); }
@@[data-edu="chalk"] h2 { font-size:3.1em; line-height:1; margin-bottom:.3em; text-shadow:.03em .03em 0 color-mix(in srgb, var(--ink) 18%, transparent); }
@@[data-edu="chalk"] h2 .accent { color:var(--a); background:linear-gradient(transparent 84%, var(--a) 84% 92%, transparent 92%) no-repeat 0 0; background-size:calc(var(--p, 1) * 100%) 100%; padding:0 .06em; }
@@[data-edu="chalk"] .slide[data-alt="1"] h2 { text-align:center; align-self:center; }
@@[data-edu="chalk"] .slide[data-alt="2"] h2 { text-align:right; align-self:flex-end; }
@@[data-edu="chalk"] .h-under { display:none; }
__CARDS__ { border-style:dashed; border-color:color-mix(in srgb, var(--ink) 55%, transparent); border-radius:255px 14px 225px 14px / 14px 225px 14px 255px; }
@@[data-edu="chalk"] .bullets li:nth-child(odd), @@[data-edu="chalk"] .steps .step:nth-child(odd), @@[data-edu="chalk"] .v-tile:nth-child(odd), @@[data-edu="chalk"] .v-card:nth-child(odd) { rotate:-.6deg; }
@@[data-edu="chalk"] .bullets li:nth-child(even), @@[data-edu="chalk"] .steps .step:nth-child(even), @@[data-edu="chalk"] .v-tile:nth-child(even), @@[data-edu="chalk"] .v-card:nth-child(even) { rotate:.5deg; border-color:color-mix(in srgb, var(--a) 70%, transparent); }
@@[data-edu="chalk"] .b-mark { width:.8em; height:.8em; border-radius:0; background:var(--a); clip-path:polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%); }
@@[data-edu="chalk"] .step-num, @@[data-edu="chalk"] .v-idx, @@[data-edu="chalk"] .v-num, @@[data-edu="chalk"] .v-dot, @@[data-edu="chalk"] .v-k { background:transparent; color:var(--a); border:.1em solid var(--a); border-radius:50% 42% 54% 46%; }
@@[data-edu="chalk"] .stat-value { text-shadow:.04em .04em 0 color-mix(in srgb, var(--ink) 22%, transparent); }
@@[data-edu="chalk"] .b-text, @@[data-edu="chalk"] .v-t, @@[data-edu="chalk"] .step-text { font-size:1.4em; }
@@[data-edu="chalk"] .decos { display:block; position:absolute; inset:0; pointer-events:none; z-index:0; }
@@[data-edu="chalk"] .slide .cover-art { background:none; border:.35vw solid color-mix(in srgb, var(--ink) 38%, transparent); width:38%; right:4%; border-radius:50% 46% 52% 48%; rotate:calc(var(--tt, 0) * 3deg); }
"""

_TERMINAL = r"""
/* ============================ FAMILY: terminal ============================ */
@@[data-edu="terminal"] { --r:.35em; --bd:.07em; --sh:none; --cardbg:color-mix(in srgb, var(--panel) 78%, var(--bg)); }
@@[data-edu="terminal"] .slide .bg::before { opacity:1; content:""; inset:0; background-image:linear-gradient(color-mix(in srgb, var(--a) 7%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--a) 7%, transparent) 1px, transparent 1px); background-size:44px 44px; -webkit-mask-image:none; mask-image:none; }
@@[data-edu="terminal"] .slide .bg::after { opacity:.6; content:""; inset:0; width:auto; height:auto; filter:none; border-radius:0; background:repeating-linear-gradient(transparent 0 3px, rgba(0,0,0,.06) 3px 4px); }
@@[data-edu="terminal"] h2 { font-size:2.35em; letter-spacing:-.01em; line-height:1.12; }
@@[data-edu="terminal"] h2::before { content:"$ "; color:var(--a); }
@@[data-edu="terminal"] h2::after { content:"_"; color:var(--a); opacity:calc(.5 + .5 * sin(var(--tt, 0) * 7)); }
@@[data-edu="terminal"] .scene.is-hero h2 { font-size:3.7em; }
__CARDS__ { border-color:color-mix(in srgb, var(--a) 55%, var(--line)); }
@@[data-edu="terminal"] .v-card::after, @@[data-edu="terminal"] .mx-card::after, @@[data-edu="terminal"] .cmp-col::after, @@[data-edu="terminal"] .stat-card::after, @@[data-edu="terminal"] .v-tile::after { content:"● ● ●"; position:absolute; top:.3em; right:.7em; font-size:.42em; letter-spacing:.15em; color:color-mix(in srgb, var(--a) 75%, transparent); }
@@[data-edu="terminal"] .b-mark { width:auto; height:auto; background:none; border:0; border-radius:0; box-shadow:none; color:var(--a); font-weight:800; font-size:1.2em; line-height:1; }
@@[data-edu="terminal"] .b-mark::before { content:">"; }
@@[data-edu="terminal"] .b-mark::after { content:none; }
@@[data-edu="terminal"] .b-mark.check::before { content:"[x]"; }
@@[data-edu="terminal"] .step-num, @@[data-edu="terminal"] .v-idx, @@[data-edu="terminal"] .v-num, @@[data-edu="terminal"] .v-k { display:inline-flex; align-items:center; width:auto; height:auto; min-width:0; padding:0; background:none; color:var(--a); border-radius:0; font-size:1em; }
@@[data-edu="terminal"] .step-num::before, @@[data-edu="terminal"] .v-idx::before, @@[data-edu="terminal"] .v-num::before { content:"["; }
@@[data-edu="terminal"] .step-num::after, @@[data-edu="terminal"] .v-idx::after, @@[data-edu="terminal"] .v-num::after { content:"]"; }
@@[data-edu="terminal"] .stat-value { font-size:3.2em; }
@@[data-edu="terminal"] .slide[data-alt="1"] .scene:not(.is-hero) { position:relative; border:.07em solid var(--a); border-radius:.5em; padding:2.3em 1.4em 1em; background:color-mix(in srgb, var(--panel) 55%, transparent); }
@@[data-edu="terminal"] .slide[data-alt="1"] .scene:not(.is-hero)::before { content:"● ● ●   ~/lesson"; position:absolute; top:.6em; left:1em; font-size:.55em; letter-spacing:.1em; color:var(--a); }
@@[data-edu="terminal"] .slide[data-alt="2"] h2 { text-align:right; align-self:flex-end; }
@@[data-edu="terminal"] .scene.is-hero .bullets li { border-radius:.3em; }
@@[data-edu="terminal"] .slide .cover-art { border-radius:.6em; width:36%; height:auto; aspect-ratio:1.4; background:repeating-linear-gradient(transparent 0 26px, color-mix(in srgb, var(--a) 18%, transparent) 26px 28px); border:.14vw solid var(--a); }
"""

_POP = r"""
/* ============================ FAMILY: pop ============================ */
@@[data-edu="pop"] { --r:.7em; --bd:.13em; --sh:.28em .28em 0 var(--ink); --cardbg:var(--panel); }
@@[data-edu="pop"] .slide .bg::before { opacity:1; content:""; inset:0; background-image:radial-gradient(color-mix(in srgb, var(--a) 26%, transparent) 2.4px, transparent 3px); background-size:22px 22px; -webkit-mask-image:linear-gradient(135deg, #000 0%, transparent 62%); mask-image:linear-gradient(135deg, #000 0%, transparent 62%); }
@@[data-edu="pop"] h2 { font-size:3.2em; line-height:.98; text-transform:uppercase; letter-spacing:.01em; rotate:-1.2deg; transform-origin:left center; text-shadow:.055em .055em 0 var(--a); margin-bottom:.45em; }
@@[data-edu="pop"] h2 .accent { color:var(--a); text-shadow:.055em .055em 0 var(--ink); }
@@[data-edu="pop"] .slide[data-alt="1"] h2 { rotate:1.2deg; text-shadow:.055em .055em 0 var(--b); }
@@[data-edu="pop"] .slide[data-alt="2"] h2 { background:var(--a); color:var(--bg); text-shadow:none; padding:.15em .6em; border-radius:.5em; border:.09em solid var(--ink); box-shadow:.12em .12em 0 var(--ink); align-self:flex-start; }
@@[data-edu="pop"] .slide[data-alt="2"] h2 .accent { color:var(--ink); text-shadow:none; }
__CARDS__ { border-color:var(--ink); }
@@[data-edu="pop"] .bullets li:nth-child(3n+2), @@[data-edu="pop"] .v-card:nth-child(3n+2), @@[data-edu="pop"] .v-tile:nth-child(3n+2), @@[data-edu="pop"] .steps .step:nth-child(3n+2) { background:color-mix(in srgb, var(--a) 24%, var(--panel)); rotate:.6deg; }
@@[data-edu="pop"] .bullets li:nth-child(3n), @@[data-edu="pop"] .v-card:nth-child(3n), @@[data-edu="pop"] .v-tile:nth-child(3n), @@[data-edu="pop"] .steps .step:nth-child(3n) { background:color-mix(in srgb, var(--b) 22%, var(--panel)); rotate:-.6deg; }
@@[data-edu="pop"] .b-mark { width:.62em; height:.62em; border-radius:50%; background:var(--a); border:.1em solid var(--ink); }
@@[data-edu="pop"] .step-num, @@[data-edu="pop"] .v-idx, @@[data-edu="pop"] .v-num, @@[data-edu="pop"] .v-dot, @@[data-edu="pop"] .v-k { background:var(--a); color:var(--ink); border:.1em solid var(--ink); box-shadow:.08em .08em 0 var(--ink); }
@@[data-edu="pop"] .stat-value { font-size:4.2em; text-shadow:.05em .05em 0 var(--ink); }
@@[data-edu="pop"] .quote { border-left-width:.5em; }
@@[data-edu="pop"] .decos { display:block; position:absolute; inset:0; pointer-events:none; z-index:0; }
@@[data-edu="pop"] .deco { stroke-width:6; stroke:var(--ink); }
@@[data-edu="pop"] .deco path { stroke:var(--ink); }
@@[data-edu="pop"] .slide .cover-art { border-radius:0; width:30%; right:4%; background:var(--a); clip-path:polygon(50% 0%, 61% 18%, 80% 8%, 78% 30%, 100% 35%, 82% 50%, 100% 65%, 78% 70%, 80% 92%, 61% 82%, 50% 100%, 39% 82%, 20% 92%, 22% 70%, 0% 65%, 18% 50%, 0% 35%, 22% 30%, 20% 8%, 39% 18%); rotate:calc(var(--tt, 0) * 14deg); }
"""

_CINEMA = r"""
/* ============================ FAMILY: cinema ============================ */
@@[data-edu="cinema"] { --r:.15em; --bd:0; --sh:none; --cardbg:linear-gradient(90deg, color-mix(in srgb, var(--a) 15%, transparent), transparent); }
@@[data-edu="cinema"] .slide .bg::before { opacity:1; content:""; inset:0; background:linear-gradient(#0b0b0d 0 7.5%, transparent 7.5% 92.5%, #0b0b0d 92.5%); background-image:linear-gradient(#0b0b0d 0 7.5%, transparent 7.5% 92.5%, #0b0b0d 92.5%); -webkit-mask-image:none; mask-image:none; z-index:2; }
@@[data-edu="cinema"] .slide .bg::after { opacity:1; content:""; inset:0; width:auto; height:auto; filter:none; border-radius:0; background:radial-gradient(ellipse at center, transparent 52%, rgba(0,0,0,.38) 100%); }
@@[data-edu="cinema"] .stage-wrap { padding:130px 130px 150px; }
@@[data-edu="cinema"].vertical .stage-wrap { padding:220px 64px 280px; }
@@[data-edu="cinema"] .brand-tag { color:#d6d6d6; }
@@[data-edu="cinema"] h2 { font-size:3em; letter-spacing:-.025em; line-height:1.04; margin-bottom:.55em; }
@@[data-edu="cinema"] h2::after { content:""; display:block; width:3em; height:.07em; margin-top:.4em; background:var(--a); }
@@[data-edu="cinema"] .slide[data-alt="1"] h2 { font-size:2.2em; letter-spacing:.14em; text-transform:uppercase; }
@@[data-edu="cinema"] .slide[data-alt="2"] h2 { text-align:center; align-self:center; }
@@[data-edu="cinema"] .slide[data-alt="2"] h2::after { margin-left:auto; margin-right:auto; }
@@[data-edu="cinema"] .scene.is-hero { justify-content:flex-end; padding-bottom:1.4em; }
@@[data-edu="cinema"] .scene.is-hero h2 { font-size:5em; }
__CARDS__ { border-left:.14em solid var(--a); padding-left:1em; }
@@[data-edu="cinema"] .v-chip { border-radius:.2em; letter-spacing:.06em; text-transform:uppercase; font-size:.95em; }
@@[data-edu="cinema"] .b-mark { width:.5em; height:.08em; border-radius:0; background:var(--a); }
@@[data-edu="cinema"] .step-num, @@[data-edu="cinema"] .v-idx, @@[data-edu="cinema"] .v-num, @@[data-edu="cinema"] .v-dot, @@[data-edu="cinema"] .v-k { background:none; color:var(--a); border-radius:0; font-size:1.5em; min-width:1.2em; height:auto; }
@@[data-edu="cinema"] .stat-value { font-size:4.4em; font-weight:400; }
@@[data-edu="cinema"] .quote p { font-style:italic; }
@@[data-edu="cinema"] .slide .cover-art { border-radius:0; width:30%; height:100%; aspect-ratio:auto; translate:none; top:0; right:10%; rotate:8deg; filter:blur(26px); background:linear-gradient(100deg, transparent, color-mix(in srgb, var(--a) 24%, transparent), transparent); }
"""

_GLASS = r"""
/* ============================ FAMILY: glass ============================ */
@@[data-edu="glass"] { --r:1.1em; --bd:.06em; --sh:inset 0 .06em 0 rgba(255,255,255,.3), 0 .5em 2em rgba(0,0,0,.18); --cardbg:color-mix(in srgb, var(--panel) 55%, transparent); }
@@[data-edu="glass"] .slide .bg::before { opacity:1; content:""; inset:0; background-image:radial-gradient(60% 55% at 12% 18%, color-mix(in srgb, var(--a) 40%, transparent), transparent 70%), radial-gradient(55% 60% at 88% 12%, color-mix(in srgb, var(--b) 34%, transparent), transparent 70%), radial-gradient(60% 55% at 70% 100%, color-mix(in srgb, var(--a) 26%, transparent), transparent 72%); -webkit-mask-image:none; mask-image:none; }
@@[data-edu="glass"] .slide .bg::after { opacity:.55; content:""; width:520px; height:520px; right:8%; top:12%; left:auto; bottom:auto; border-radius:50%; background:radial-gradient(circle, color-mix(in srgb, var(--b) 45%, transparent), transparent 70%); filter:blur(30px); scale:calc(1 + sin(var(--tt, 0)) * .08); }
@@[data-edu="glass"] h2 { font-size:2.5em; background:linear-gradient(90deg, var(--ink), color-mix(in srgb, var(--a) 72%, var(--ink))); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; padding-bottom:.08em; }
@@[data-edu="glass"] h2 .accent { -webkit-text-fill-color:var(--a); }
@@[data-edu="glass"] .slide[data-alt="1"] h2 { text-align:center; align-self:center; }
@@[data-edu="glass"] .slide[data-alt="2"] .scene:not(.is-hero) { flex-direction:column-reverse; }
@@[data-edu="glass"] .slide[data-alt="2"] h2 { margin:.6em 0 0; font-size:2em; }
__CARDS__ { border-color:color-mix(in srgb, var(--ink) 18%, transparent); }
@@[data-edu="glass"] .bullets li:first-child, @@[data-edu="glass"] .v-card:first-child, @@[data-edu="glass"] .steps .step:first-child { background:color-mix(in srgb, var(--a) 22%, transparent); }
@@[data-edu="glass"] .b-mark { width:.7em; height:.7em; border-radius:50%; background:linear-gradient(135deg, var(--a), var(--b)); }
@@[data-edu="glass"] .step-num, @@[data-edu="glass"] .v-idx, @@[data-edu="glass"] .v-num, @@[data-edu="glass"] .v-dot, @@[data-edu="glass"] .v-k { background:linear-gradient(135deg, var(--a), var(--b)); border-radius:50%; color:var(--bg); }
@@[data-edu="glass"] .stat-value { background:linear-gradient(90deg, var(--a), var(--b)); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
@@[data-edu="glass"] .scene.is-hero h2 { font-size:4.6em; }
@@[data-edu="glass"] .slide .cover-art { width:54%; right:-8%; filter:blur(6px); }
"""

_MAGAZINE = r"""
/* ============================ FAMILY: magazine ============================ */
@@[data-edu="magazine"] { --r:0; --bd:0; --sh:none; --cardbg:transparent; }
@@[data-edu="magazine"] .slide .bg::before { opacity:1; content:""; inset:0 auto 0 100px; width:3px; height:auto; background:color-mix(in srgb, var(--ink) 85%, transparent); background-image:none; -webkit-mask-image:none; mask-image:none; }
@@[data-edu="magazine"] .slide[data-alt="1"] .bg::before { inset:0 100px 0 auto; }
@@[data-edu="magazine"] .slide[data-alt="2"] .bg::before { inset:34% 0 auto 0; width:100%; height:3px; }
@@[data-edu="magazine"] .slide[data-index="0"] .bg::before { opacity:0; }
@@[data-edu="magazine"] .stage-wrap { padding-left:150px; }
@@[data-edu="magazine"] .slide[data-alt="1"] .stage-wrap { padding-left:96px; padding-right:150px; }
@@[data-edu="magazine"] .slide[data-alt="2"] .stage-wrap { padding-left:96px; }
@@[data-edu="magazine"].vertical .stage-wrap, @@[data-edu="magazine"].vertical .slide[data-alt="1"] .stage-wrap, @@[data-edu="magazine"].vertical .slide[data-alt="2"] .stage-wrap { padding:120px 64px 210px 100px; }
@@[data-edu="magazine"].vertical .slide .bg::before, @@[data-edu="magazine"].vertical .slide[data-alt="1"] .bg::before, @@[data-edu="magazine"].vertical .slide[data-alt="2"] .bg::before { inset:0 auto 0 52px; width:3px; height:auto; }
@@[data-edu="magazine"] h2 { font-size:3.4em; letter-spacing:-.035em; line-height:.98; padding-bottom:.18em; margin-bottom:.45em; border-bottom:.09em solid var(--ink); }
@@[data-edu="magazine"] h2 .accent { color:var(--a); font-style:italic; }
@@[data-edu="magazine"] .scene.is-hero h2 { font-size:5em; border-bottom:0; }
@@[data-edu="magazine"].vertical h2 { font-size:2.6em; }
@@[data-edu="magazine"] .bullets, @@[data-edu="magazine"] .steps, @@[data-edu="magazine"] .v-rail, @@[data-edu="magazine"] .v-agenda, @@[data-edu="magazine"] .v-col { counter-reset:mg; }
@@[data-edu="magazine"] .bullets li, @@[data-edu="magazine"] .steps .step, @@[data-edu="magazine"] .v-rail li, @@[data-edu="magazine"] .v-agenda li, @@[data-edu="magazine"] .v-col li { counter-increment:mg; border-top:.07em solid color-mix(in srgb, var(--ink) 80%, transparent); padding-left:0; }
@@[data-edu="magazine"] .bullets li::before, @@[data-edu="magazine"] .steps .step::before, @@[data-edu="magazine"] .v-rail li::before, @@[data-edu="magazine"] .v-agenda li::before, @@[data-edu="magazine"] .v-col li::before { content:counter(mg, decimal-leading-zero); font-family:var(--hf); font-weight:var(--hw, 700); font-size:2.3em; line-height:.9; color:transparent; -webkit-text-stroke:.03em var(--a); flex:none; min-width:1.5em; }
@@[data-edu="magazine"] .scene.is-hero .bullets li::before { display:none; }
@@[data-edu="magazine"] .b-mark, @@[data-edu="magazine"] .step-num, @@[data-edu="magazine"] .v-idx, @@[data-edu="magazine"] .v-num { display:none; }
@@[data-edu="magazine"] .v-card, @@[data-edu="magazine"] .v-tile { border-top:.2em solid var(--ink); background:color-mix(in srgb, var(--a) 7%, var(--bg)); padding-top:.7em; }
@@[data-edu="magazine"] .cmp-col, @@[data-edu="magazine"] .stat-card, @@[data-edu="magazine"] .mx-card { border-top:.2em solid var(--ink); background:color-mix(in srgb, var(--a) 7%, var(--bg)); }
@@[data-edu="magazine"] .stat-value { font-size:4.6em; color:transparent; -webkit-text-stroke:.03em var(--a); }
@@[data-edu="magazine"] .quote { border-left:0; padding-left:0; }
@@[data-edu="magazine"] .quote p { font-style:italic; }
@@[data-edu="magazine"] .slide .cover-art { border-radius:0; width:24%; aspect-ratio:3/4; right:6%; background:var(--a); rotate:3deg; box-shadow:-1.2vw 1.2vw 0 color-mix(in srgb, var(--ink) 85%, transparent); }
"""

_BLOCKS = (_CHALK, _TERMINAL, _POP, _CINEMA, _GLASS, _MAGAZINE)


def build_css() -> str:
    """Raw CSS with ``@@`` placeholders, card selector lists expanded."""
    return "".join(
        block.replace("__CARDS__", _cards(fam)) for fam, block in zip(EXTRA_FAMILIES, _BLOCKS)
    )
