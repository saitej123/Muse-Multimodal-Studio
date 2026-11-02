"""Unique layout templates (geometry + type + sequence) — not color clones.

HyperFrames frame-presets and agent skills are mapped to VIDEO_STYLES keys.
Palettes live in VIDEO_THEMES and are chosen separately via the Colors strip.
"""
from __future__ import annotations

# Geometry modes consumed by slideshow CSS (`body[data-compose]`) and card previews.
COMPOSE_MODES = (
    "stack", "split", "lower_third", "kinetic_center", "bento", "kpi",
    "caption", "rail", "quote", "letterbox", "chalkboard", "terminal",
    "magazine", "swiss", "mega_type", "dual", "mosaic", "cards_stack",
    "broadcast", "device", "poster", "ticker", "chapters", "glass",
    "neon_sign", "blueprint", "funnel", "cycle", "kanban", "polaroid",
    "filmstrip", "subway", "news_lower", "pip", "quad",
    # Remotion 2026 motion-graphic frames (unique HTML, not palettes).
    "audiogram", "karaoke", "scramble", "counter_ring", "code_hike",
    "stargazer", "travel_map", "mask_reveal", "glitch_type", "progress_track",
    "word_cloud", "zoom_punch", "safe_overlay", "spring_cards", "news_stack",
    "podcast_tile", "repo_stars", "donut_stat", "light_leak", "particle_field",
)

REMOTION_COMPOSE = COMPOSE_MODES[-20:]

# Existing VIDEO_STYLES keys → compose so Promo Sprint ≠ Kinetic Center.
EXISTING_LAYOUT_MODES: dict[str, str] = {
    "modern": "stack", "minimal": "stack", "editorial": "magazine",
    "bold": "mega_type", "explainer": "stack", "documentary": "letterbox",
    "teardown": "dual", "tutorial": "chapters", "whiteboard": "chalkboard",
    "cinematic": "letterbox", "neon": "neon_sign", "blueprint": "blueprint",
    "playful": "glass", "terminal": "terminal", "hybrid": "stack",
    "hybrid_kinetic": "kinetic_center", "hybrid_data": "kpi",
    "hybrid_story": "quote", "kinetic": "kinetic_center", "dataviz": "kpi",
    "device": "device", "broadcast": "broadcast", "cards": "cards_stack",
    "pitch": "poster", "corporate": "stack", "glass": "glass", "saas": "bento",
    "gamma": "cards_stack", "keynote": "mega_type", "slides": "stack",
    "notion": "stack", "geo_navy": "swiss", "coral_split": "split",
    "blush_soft": "glass", "mosaic": "mosaic", "process": "rail",
    "agenda": "chapters", "rainbow_bar": "rail", "circle_stack": "mosaic",
    "hex_grid": "mosaic", "wave_soft": "stack", "swiss_pulse": "swiss",
    "velvet_std": "magazine", "deconstructed": "poster",
    "maximalist": "mega_type", "data_drift": "mosaic",
    "soft_signal": "magazine", "folk_freq": "mosaic",
    "shadow_cut": "letterbox", "kinetic_center": "kinetic_center",
    "lower_third": "lower_third", "promo_sprint": "split",
    "caption_pop": "caption", "chart_race": "kpi", "logo_intro": "poster",
    "bento": "bento", "big_stat": "kpi", "quote_pull": "quote",
    "timeline_rail": "rail", "split_media": "split",
    "proof_duo": "dual", "kpi_strip": "kpi", "stack_cards": "cards_stack",
}

# Curated Featured chip (layout keys only — not layout×color).
FEATURED_LAYOUT_ORDER: tuple[str, ...] = (
    "whiteboard", "hybrid", "hybrid_kinetic", "hybrid_data", "hybrid_story",
    "swiss_pulse", "velvet_std", "maximalist", "data_drift", "soft_signal",
    "folk_freq", "shadow_cut", "deconstructed",
    "kinetic_center", "lower_third", "promo_sprint", "caption_pop",
    "chart_race", "logo_intro",
    "hf_biennale", "hf_capsule", "hf_cobalt", "hf_product_launch",
    "bento", "big_stat", "quote_pull", "timeline_rail", "split_media",
    "proof_duo", "kpi_strip", "stack_cards",
    "geo_navy", "word_slam", "title_only",
)
FEATURED_LAYOUT_KEYS = set(FEATURED_LAYOUT_ORDER)

_FONTS: dict[str, str] = {
    "Inter": "Inter,Segoe UI,system-ui,sans-serif",
    "Space Grotesk": '"Space Grotesk",Inter,system-ui,sans-serif',
    "Poppins": "Poppins,Inter,system-ui,sans-serif",
    "Oswald": "Oswald,Impact,sans-serif",
    "IBM Plex Mono": '"IBM Plex Mono",ui-monospace,monospace',
    "Montserrat": "Montserrat,Inter,sans-serif",
    "Playfair Display": '"Playfair Display",Georgia,serif',
    "DM Sans": '"DM Sans",Inter,sans-serif',
    "Figtree": "Figtree,Inter,sans-serif",
    "Manrope": "Manrope,Inter,sans-serif",
    "Outfit": "Outfit,Inter,sans-serif",
    "Work Sans": '"Work Sans",Inter,sans-serif',
    "Rubik": "Rubik,Inter,sans-serif",
    "Nunito": "Nunito,Inter,sans-serif",
    "Anton": "Anton,Impact,sans-serif",
    "Newsreader": "Newsreader,Georgia,serif",
    "Archivo": "Archivo,Inter,sans-serif",
    "Syne": "Syne,Inter,sans-serif",
    "Sora": "Sora,Inter,sans-serif",
    "Fraunces": "Fraunces,Georgia,serif",
    "Bricolage Grotesque": '"Bricolage Grotesque",Inter,sans-serif',
    "Plus Jakarta Sans": '"Plus Jakarta Sans",Inter,sans-serif',
    "Literata": "Literata,Georgia,serif",
    "Barlow": "Barlow,Inter,sans-serif",
    "Instrument Serif": '"Instrument Serif","Playfair Display",Georgia,serif',
    "Space Mono": '"Space Mono",ui-monospace,monospace',
    "JetBrains Mono": '"JetBrains Mono",ui-monospace,monospace',
    "Caveat": "Caveat,cursive",
    "Fredoka": "Fredoka,Nunito,sans-serif",
}

_COMPOSE_TOKENS: dict[str, dict[str, str]] = {
    "stack": {
        "h2_weight": "800", "h2_scale": "1.04", "h2_spacing": "-.02em",
        "card_radius": "16px", "card_border": "1px",
        "card_shadow": "0 16px 40px rgba(0,0,0,.28)",
        "panel_alpha": "1", "grid_opacity": ".35", "blob_opacity": ".18",
        "uppercase_kicker": "uppercase",
    },
    "split": {
        "h2_weight": "750", "h2_scale": "1.02", "h2_spacing": "-.03em",
        "card_radius": "18px", "card_border": "1px",
        "card_shadow": "0 20px 48px rgba(0,0,0,.3)",
        "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".2",
        "uppercase_kicker": "uppercase",
    },
    "swiss": {
        "h2_weight": "800", "h2_scale": "1.08", "h2_spacing": "-.06em",
        "card_radius": "0", "card_border": "2px",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": ".85", "blob_opacity": "0",
        "uppercase_kicker": "uppercase",
    },
    "magazine": {
        "h2_weight": "500", "h2_scale": "1.12", "h2_spacing": "-.03em",
        "card_radius": "2px", "card_border": "1px",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".08",
        "uppercase_kicker": "uppercase",
    },
    "mega_type": {
        "h2_weight": "900", "h2_scale": "1.28", "h2_spacing": "-.06em",
        "card_radius": "0", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "0.4", "grid_opacity": "0", "blob_opacity": ".12",
        "uppercase_kicker": "uppercase",
    },
    "kinetic_center": {
        "h2_weight": "800", "h2_scale": "1.16", "h2_spacing": "-.05em",
        "card_radius": "8px", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "0.2", "grid_opacity": "0", "blob_opacity": ".28",
        "uppercase_kicker": "none",
    },
    "lower_third": {
        "h2_weight": "700", "h2_scale": "0.92", "h2_spacing": "0",
        "card_radius": "4px", "card_border": "0",
        "card_shadow": "0 -8px 32px rgba(0,0,0,.4)",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".1",
        "uppercase_kicker": "uppercase",
    },
    "caption": {
        "h2_weight": "800", "h2_scale": "1.2", "h2_spacing": "-.04em",
        "card_radius": "12px", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "0.15", "grid_opacity": "0", "blob_opacity": ".22",
        "uppercase_kicker": "none",
    },
    "kpi": {
        "h2_weight": "800", "h2_scale": "0.88", "h2_spacing": "-.04em",
        "card_radius": "20px", "card_border": "1px",
        "card_shadow": "0 24px 50px rgba(0,0,0,.28)",
        "panel_alpha": "1", "grid_opacity": ".15", "blob_opacity": ".2",
        "uppercase_kicker": "uppercase",
    },
    "bento": {
        "h2_weight": "750", "h2_scale": "1.0", "h2_spacing": "-.03em",
        "card_radius": "22px", "card_border": "1px",
        "card_shadow": "0 12px 28px rgba(0,0,0,.16)",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".12",
        "uppercase_kicker": "none",
    },
    "chalkboard": {
        "h2_weight": "600", "h2_scale": "1.1", "h2_spacing": "0",
        "card_radius": "2px", "card_border": "1px",
        "card_shadow": "none",
        "panel_alpha": "0.35", "grid_opacity": ".2", "blob_opacity": "0",
        "uppercase_kicker": "none",
    },
    "terminal": {
        "h2_weight": "600", "h2_scale": "0.92", "h2_spacing": "0",
        "card_radius": "10px", "card_border": "1px",
        "card_shadow": "0 18px 40px rgba(0,0,0,.45)",
        "panel_alpha": "1", "grid_opacity": ".4", "blob_opacity": "0",
        "uppercase_kicker": "uppercase",
    },
    "letterbox": {
        "h2_weight": "500", "h2_scale": "1.14", "h2_spacing": ".04em",
        "card_radius": "0", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "0.2", "grid_opacity": "0", "blob_opacity": ".16",
        "uppercase_kicker": "uppercase",
    },
    "poster": {
        "h2_weight": "900", "h2_scale": "1.22", "h2_spacing": "-.05em",
        "card_radius": "0", "card_border": "4px",
        "card_shadow": "8px 8px 0 currentColor",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".1",
        "uppercase_kicker": "uppercase",
    },
    "glass": {
        "h2_weight": "650", "h2_scale": "1.06", "h2_spacing": "-.02em",
        "card_radius": "28px", "card_border": "1px",
        "card_shadow": "0 20px 50px rgba(0,0,0,.18)",
        "panel_alpha": "0.55", "grid_opacity": "0", "blob_opacity": ".28",
        "uppercase_kicker": "none",
    },
    "cards_stack": {
        "h2_weight": "750", "h2_scale": "1.02", "h2_spacing": "-.02em",
        "card_radius": "16px", "card_border": "1px",
        "card_shadow": "8px 12px 0 color-mix(in srgb, var(--a) 22%, transparent)",
        "panel_alpha": "1", "grid_opacity": ".06", "blob_opacity": ".12",
        "uppercase_kicker": "none",
    },
    "mosaic": {
        "h2_weight": "700", "h2_scale": "1.0", "h2_spacing": "-.02em",
        "card_radius": "14px", "card_border": "1px",
        "card_shadow": "0 10px 24px rgba(0,0,0,.2)",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".14",
        "uppercase_kicker": "uppercase",
    },
    "dual": {
        "h2_weight": "750", "h2_scale": "1.0", "h2_spacing": "-.02em",
        "card_radius": "16px", "card_border": "1px",
        "card_shadow": "0 16px 36px rgba(0,0,0,.22)",
        "panel_alpha": "1", "grid_opacity": ".1", "blob_opacity": ".12",
        "uppercase_kicker": "uppercase",
    },
    "rail": {
        "h2_weight": "700", "h2_scale": "0.96", "h2_spacing": "-.02em",
        "card_radius": "999px", "card_border": "1px",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".1",
        "uppercase_kicker": "uppercase",
    },
    "quote": {
        "h2_weight": "500", "h2_scale": "1.18", "h2_spacing": "-.03em",
        "card_radius": "0", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "0", "grid_opacity": "0", "blob_opacity": ".1",
        "uppercase_kicker": "none",
    },
    "broadcast": {
        "h2_weight": "800", "h2_scale": "0.9", "h2_spacing": "0",
        "card_radius": "2px", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".08",
        "uppercase_kicker": "uppercase",
    },
    "device": {
        "h2_weight": "700", "h2_scale": "0.94", "h2_spacing": "-.02em",
        "card_radius": "28px", "card_border": "8px",
        "card_shadow": "0 28px 60px rgba(0,0,0,.4)",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".16",
        "uppercase_kicker": "none",
    },
    "chapters": {
        "h2_weight": "750", "h2_scale": "1.06", "h2_spacing": "-.03em",
        "card_radius": "12px", "card_border": "1px",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".1",
        "uppercase_kicker": "uppercase",
    },
    "ticker": {
        "h2_weight": "700", "h2_scale": "0.86", "h2_spacing": "0",
        "card_radius": "0", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": "0",
        "uppercase_kicker": "uppercase",
    },
    "neon_sign": {
        "h2_weight": "800", "h2_scale": "1.14", "h2_spacing": ".08em",
        "card_radius": "4px", "card_border": "1px",
        "card_shadow": "0 0 28px color-mix(in srgb, var(--a) 55%, transparent)",
        "panel_alpha": "0.25", "grid_opacity": ".2", "blob_opacity": ".45",
        "uppercase_kicker": "uppercase",
    },
    "blueprint": {
        "h2_weight": "500", "h2_scale": "0.94", "h2_spacing": ".04em",
        "card_radius": "0", "card_border": "1px",
        "card_shadow": "none",
        "panel_alpha": "0.2", "grid_opacity": "1", "blob_opacity": "0",
        "uppercase_kicker": "uppercase",
    },
    "funnel": {
        "h2_weight": "750", "h2_scale": "1.0", "h2_spacing": "-.02em",
        "card_radius": "8px", "card_border": "1px",
        "card_shadow": "0 10px 24px rgba(0,0,0,.18)",
        "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".1",
        "uppercase_kicker": "uppercase",
    },
    "cycle": {
        "h2_weight": "700", "h2_scale": "1.0", "h2_spacing": "-.02em",
        "card_radius": "999px", "card_border": "2px",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".12",
        "uppercase_kicker": "uppercase",
    },
    "kanban": {
        "h2_weight": "700", "h2_scale": "0.92", "h2_spacing": "-.01em",
        "card_radius": "10px", "card_border": "1px",
        "card_shadow": "0 8px 18px rgba(0,0,0,.12)",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".08",
        "uppercase_kicker": "uppercase",
    },
    "polaroid": {
        "h2_weight": "600", "h2_scale": "1.0", "h2_spacing": "0",
        "card_radius": "4px", "card_border": "10px",
        "card_shadow": "0 18px 32px rgba(0,0,0,.22)",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".1",
        "uppercase_kicker": "none",
    },
    "filmstrip": {
        "h2_weight": "700", "h2_scale": "0.9", "h2_spacing": ".08em",
        "card_radius": "0", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": "0",
        "uppercase_kicker": "uppercase",
    },
    "subway": {
        "h2_weight": "800", "h2_scale": "1.0", "h2_spacing": "-.04em",
        "card_radius": "999px", "card_border": "3px",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".08",
        "uppercase_kicker": "uppercase",
    },
    "news_lower": {
        "h2_weight": "800", "h2_scale": "0.88", "h2_spacing": "0",
        "card_radius": "0", "card_border": "0",
        "card_shadow": "none",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": "0",
        "uppercase_kicker": "uppercase",
    },
    "pip": {
        "h2_weight": "700", "h2_scale": "1.04", "h2_spacing": "-.03em",
        "card_radius": "16px", "card_border": "2px",
        "card_shadow": "0 24px 48px rgba(0,0,0,.35)",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".14",
        "uppercase_kicker": "none",
    },
    "quad": {
        "h2_weight": "750", "h2_scale": "0.92", "h2_spacing": "-.02em",
        "card_radius": "12px", "card_border": "1px",
        "card_shadow": "0 10px 22px rgba(0,0,0,.16)",
        "panel_alpha": "1", "grid_opacity": "0", "blob_opacity": ".1",
        "uppercase_kicker": "uppercase",
    },
}

# key, label, category, compose, font, template, example, description, theme, uses
_ROWS: tuple[tuple[str, str, str, str, str, str, str, str, str, str], ...] = (
    # --- HyperFrames frame-presets (heygen-com/hyperframes) ---
    ("hf_biennale", "Biennale Yellow", "hyper", "magazine", "Instrument Serif",
     "Cover plate → yellow bloom → colophon", "Museum catalogue · literary promo",
     "HyperFrames Biennale: parchment ground, indigo ink, solar yellow underprint, hairline rules.",
     "ivory", "Exhibition · catalogue · essay"),
    ("hf_blockframe", "BlockFrame", "hyper", "poster", "Inter",
     "Hard offset → candy block → stamp", "Neobrutal product punch",
     "HyperFrames BlockFrame: 4px ink borders, 8px hard shadows, uppercase Inter, square corners.",
     "sunset", "Launch sting · loud promo"),
    ("hf_blue_pro", "Blue Professional", "hyper", "stack", "Barlow",
     "Agenda → insight → decision", "Consulting cream canvas",
     "HyperFrames Blue Professional: cream boardroom frames, navy rules, restrained type.",
     "paper", "QBR · consulting deck"),
    ("hf_bold_poster", "Bold Poster", "hyper", "poster", "Anton",
     "Giant verb → subline → mark", "Street-poster claim",
     "HyperFrames Bold Poster: full-bleed verb, tight tracking, poster margins.",
     "sunset", "Campaign · statement"),
    ("hf_broadside", "Broadside", "hyper", "magazine", "Newsreader",
     "Masthead → columns → kicker", "Broadsheet editorial",
     "HyperFrames Broadside: newspaper masthead, multi-column body, ink rules.",
     "ivory", "Press · long read"),
    ("hf_capsule", "Capsule", "hyper", "glass", "Syne",
     "Title pill → candy chips → CTA pill", "Playful editorial pills",
     "HyperFrames Capsule: every container a pill, cream canvas, Bodoni-energy display via Syne.",
     "mint", "Friendly brand · feature tour"),
    ("hf_cartesian", "Cartesian", "hyper", "swiss", "Playfair Display",
     "Hairline grid → display → colophon", "Museum-catalog compass",
     "HyperFrames Cartesian: 1px taupe grid, Playfair + Inter, zero shadow, drafted rings.",
     "paper", "Quiet authority · catalog"),
    ("hf_cobalt", "Cobalt Grid", "hyper", "swiss", "Newsreader",
     "Hairlines → graph paper → QR patch", "Two-color risograph report",
     "HyperFrames Cobalt Grid: cream paper, cobalt-only ink, permanent graph paper, serif 400.",
     "snow", "Trend report · systems"),
    ("hf_code_ed", "Code Editorial", "hyper", "terminal", "IBM Plex Mono",
     "Gutter → snippet → annotation", "Editorial code frames",
     "HyperFrames Code Editorial: mono chrome, snippet gutters, annotated diffs as slides.",
     "slate", "Devlog · API teach"),
    ("hf_coral_hf", "Coral Frame", "hyper", "split", "Poppins",
     "Warm hero → split proof → pill CTA", "Coral marketing split",
     "HyperFrames Coral: warm split hero, rounded marketing cards, energetic CTA.",
     "sunset", "Product marketing"),
    ("hf_creative", "Creative Mode", "hyper", "mosaic", "Bricolage Grotesque",
     "Mood tiles → type layers → stamp", "Studio moodboard frames",
     "HyperFrames Creative Mode: overlapping tiles, display layers, studio energy.",
     "nebula", "Brand film · mood"),
    ("hf_daisy", "Daisy Days", "hyper", "glass", "Fraunces",
     "Soft bloom → italic word → garden chips", "Pastel editorial garden",
     "HyperFrames Daisy Days: sun-bleached pastels, italic key word, airy chips.",
     "mint", "Lifestyle · wellness"),
    ("hf_forest", "Editorial Forest", "hyper", "magazine", "Literata",
     "Canopy title → body column → leaf rule", "Forest literary magazine",
     "HyperFrames Editorial Forest: deep greens as chrome, serif display, magazine column.",
     "emerald", "Nature essay · journal"),
    # --- HyperFrames agent skills as templates ---
    ("hf_product_launch", "Product Launch", "motion", "split", "Plus Jakarta Sans",
     "Logo sting → features → proof → CTA", "HyperFrames /product-launch-video",
     "Skill template: feature sprint, screenshot beats, CTA sting — not a color clone of Kinetic.",
     "aurora", "Launch video · SaaS promo"),
    ("hf_faceless", "Faceless Explainer", "teach", "kinetic_center", "Sora",
     "Hook type → diagram → recap lockup", "HyperFrames /faceless-explainer",
     "Skill template: VO-led type + diagrams, no talking head, center-lock claims.",
     "midnight", "Faceless YouTube"),
    ("hf_captions", "Embedded Captions", "motion", "caption", "Poppins",
     "Burned-in line → word pop → hold", "HyperFrames /embedded-captions",
     "Skill template: captions are the layout — karaoke fit, safe-area type, no lower-third chrome.",
     "sunset", "Shorts · Reels · silent autoplay"),
    ("hf_talking_head", "Talking Head Recut", "story", "lower_third", "Oswald",
     "Name plate → chapter chip → sting", "HyperFrames /talking-head-recut",
     "Skill template: recut interview with name/title plates and chapter chips.",
     "midnight", "Interview · podcast clip"),
    ("hf_motion_gfx", "Motion Graphics", "motion", "kinetic_center", "Space Grotesk",
     "Shape sting → type lock → wipe", "HyperFrames /motion-graphics",
     "Skill template: shape language + type lockups, motion-first, not a palette swap.",
     "cyber", "Opener · bumper"),
    ("hf_pr_video", "PR to Video", "story", "news_lower", "Barlow",
     "Headline → quote → logo row", "HyperFrames /pr-to-video",
     "Skill template: press-release beats as news frames with ticker + quote.",
     "snow", "Announcement · press"),
    ("hf_slideshow_sk", "Skill Slideshow", "content", "chapters", "DM Sans",
     "Section → beat → recap", "HyperFrames /slideshow",
     "Skill template: chaptered slideshow with numbered section plates.",
     "paper", "Lesson · briefing"),
    ("hf_music_sync", "Music to Video", "story", "filmstrip", "Syne",
     "Beat grid → lyric card → drop", "HyperFrames /music-to-video",
     "Skill template: lyric/beat-synced cards on a filmstrip, drop on downbeat.",
     "nebula", "Lyric video · montage"),
    # --- Remotion / motion (unique geometries) ---
    ("word_slam", "Word Slam", "motion", "mega_type", "Anton",
     "One word → slam → hold", "Type hits the frame",
     "Single-word impact lockup. Geometry is the word, not a recolored bar.",
     "cyber", "Hook · trailer beat"),
    ("typewriter_line", "Typewriter Line", "motion", "caption", "IBM Plex Mono",
     "Caret → type → blink hold", "Mono line that writes itself",
     "One writing line with caret; body copy never wraps into a card stack.",
     "slate", "CLI story · thesis line"),
    ("split_stinger", "Split Stinger", "motion", "split", "Oswald",
     "Wipe split → dual claim → merge", "Vertical wipe into two claims",
     "Frame splits; two claims live on opposite halves, then merge.",
     "sunset", "Versus · reveal"),
    ("end_card", "End Card", "motion", "poster", "Montserrat",
     "Title lock → subscribe row → next", "YouTube end-screen geometry",
     "End-screen tiles + title lockup, not a feature-sprint clone.",
     "midnight", "Subscribe · next video"),
    ("bumper_ident", "Bumper Ident", "motion", "poster", "Syne",
     "Mark → wordmark → cut", "2-second channel ident",
     "Centered mark then wordmark; empty mid-frame on purpose.",
     "nebula", "Channel sting"),
    ("iris_open", "Iris Open", "motion", "kinetic_center", "Outfit",
     "Circle iris → claim → settle", "Iris reveal of the claim",
     "Circular mask opens onto a centered claim.",
     "aurora", "Cold open"),
    ("match_cut", "Match Cut", "motion", "dual", "Space Grotesk",
     "Shape A → morph → Shape B", "Graphic match between beats",
     "Two aligned objects; the cut is the layout.",
     "cyber", "Transition beat"),
    ("coverflow_row", "Coverflow", "motion", "filmstrip", "Figtree",
     "Peek stack → focus card → recede", "Coverflow of idea cards",
     "Perspective row with one focused card; neighbors peek.",
     "paper", "Feature carousel"),
    ("cube_spin", "Cube Spin", "motion", "quad", "Sora",
     "Face A → rotate → Face B", "Cube faces as beats",
     "Four faces; each rotate shows a new beat.",
     "midnight", "Four-beat explainer"),
    ("pip_overlay", "PiP Overlay", "motion", "pip", "Inter",
     "Main claim → inset proof → hold", "Picture-in-picture proof",
     "Primary type with a corner inset for a metric or still.",
     "aurora", "Demo + number"),
    ("ticker_news", "News Ticker", "motion", "ticker", "Barlow",
     "Headline → crawling strip → sting", "Broadcast ticker geometry",
     "Headline plate plus a crawling strip; not a lower-third clone.",
     "sunset", "News brief"),
    ("scoreboard", "Scoreboard", "motion", "kpi", "Oswald",
     "Home · away → clock → stat", "Sports score bug",
     "Dual scores + clock. Layout is a scoreboard, not KPI cards.",
     "emerald", "Comparison · live stat"),
    ("weather_card", "Weather Card", "motion", "bento", "Nunito",
     "Hero temp → 4-up forecast", "Forecast bento",
     "Giant reading + four small cells — weather-app geometry for any metric.",
     "mint", "Forecast · trend"),
    ("sports_lower", "Sports Lower", "motion", "news_lower", "Oswald",
     "Name + number bar → hold", "Athlete name / number plate",
     "Name, number, and team chip on a sports lower — distinct from news lower-third.",
     "midnight", "Guest ID · player"),
    ("mid_roll", "Mid-roll Bumper", "motion", "letterbox", "Anton",
     "Black · title card · resume", "Chapter bumper",
     "Letterboxed chapter card between scenes.",
     "mono", "Act break"),
    ("safe_area_type", "Safe Area Type", "motion", "caption", "Poppins",
     "Title-safe box → fit → hold", "Title-safe caption box",
     "Type locked inside broadcast title-safe; wrapping is the feature.",
     "snow", "TV-safe shorts"),
    # --- Content layouts ---
    ("faq_accordion", "FAQ Accordion", "content", "stack", "Inter",
     "Question → answer stack → next Q", "One Q, one A per beat",
     "Stacked Q/A plates. Not a bullet list — question is the kicker.",
     "paper", "FAQ · objection handling"),
    ("pricing_tiers", "Pricing Tiers", "content", "quad", "Plus Jakarta Sans",
     "3-up tiers → highlight → CTA", "SaaS pricing columns",
     "Three equal columns with a highlighted middle — pricing geometry.",
     "snow", "Pricing · plans"),
    ("roadmap_map", "Roadmap Map", "content", "rail", "DM Sans",
     "Now → next → later", "Release train rail",
     "Horizontal now/next/later stations, not a generic timeline clone.",
     "aurora", "Roadmap"),
    ("org_chart", "Org Chart", "content", "mosaic", "Barlow",
     "Root → branches → leaves", "Hierarchy tiles",
     "Parent node above children; org geometry for any tree.",
     "paper", "Team · taxonomy"),
    ("funnel_drop", "Funnel Drop", "content", "funnel", "Manrope",
     "Wide → mid → narrow", "Conversion funnel",
     "Tapered bands. Width is the data.",
     "midnight", "Funnel · pipeline"),
    ("pyramid_levels", "Pyramid", "content", "funnel", "Montserrat",
     "Base → mid → peak", "Hierarchy pyramid",
     "Inverted funnel (pyramid). Levels, not a list.",
     "ivory", "Maslow · strategy"),
    ("venn_overlap", "Venn Overlap", "content", "cycle", "Figtree",
     "A · B · overlap", "Two-set overlap",
     "Two circles and the shared claim in the overlap.",
     "mint", "Overlap · AND"),
    ("cycle_loop", "Cycle Loop", "content", "cycle", "Outfit",
     "1 → 2 → 3 → 1", "Circular process",
     "Nodes on a ring with directional arrows.",
     "aurora", "Loop · flywheel"),
    ("kanban_board", "Kanban Board", "content", "kanban", "Inter",
     "Todo · doing · done", "Three swimlanes",
     "Three columns of cards. Status is the layout.",
     "paper", "Status · WIP"),
    ("gantt_bars", "Gantt Bars", "content", "rail", "IBM Plex Mono",
     "Tracks → bars → now line", "Schedule tracks",
     "Named tracks with duration bars — not a chart-race clone.",
     "slate", "Plan · schedule"),
    ("polaroid_wall", "Polaroid Wall", "content", "polaroid", "Caveat",
     "Tilted stills → caption → pin", "Photo-wall evidence",
     "Tilted polaroid frames with handwritten captions.",
     "ivory", "Evidence · mood"),
    ("filmstrip_row", "Filmstrip Row", "content", "filmstrip", "Oswald",
     "Frame 1–5 sprocket row", "35mm beat row",
     "Sprocketed stills in a row; one beat per frame.",
     "mono", "Sequence · process"),
    ("subway_map", "Subway Map", "content", "subway", "Barlow",
     "Lines · transfers · stop", "Transit-map ideas",
     "Colored lines and transfer nodes — system map, not a flowchart box.",
     "snow", "Architecture · routes"),
    ("periodic_cells", "Periodic Cells", "content", "mosaic", "IBM Plex Mono",
     "Element tiles → highlight → family", "Periodic-table mosaic",
     "Tight cell grid with atomic-number style labels.",
     "paper", "Taxonomy · catalog"),
    ("recipe_steps", "Recipe Steps", "content", "chapters", "Nunito",
     "Ingredients → method → plate", "Kitchen-card lesson",
     "Ingredients rail then numbered method — cooking geometry for any procedure.",
     "mint", "How-to · lab"),
    ("syllabus_week", "Syllabus Week", "content", "kanban", "Literata",
     "Week n → outcomes → reading", "Course week plate",
     "Week number, outcomes, reading list as three bands.",
     "ivory", "Course · cohort"),
    ("exam_prompt", "Exam Prompt", "content", "chalkboard", "Inter",
     "Question · time · rubric", "Exam-paper frame",
     "Prompt with time box and rubric chips — assessment geometry.",
     "snow", "Quiz · challenge"),
    ("lab_notes", "Lab Notes", "content", "terminal", "JetBrains Mono",
     "Hypothesis → method → result", "Lab-notebook page",
     "Ruled notebook + mono result block.",
     "paper", "Experiment"),
    ("legal_clause", "Legal Clause", "content", "magazine", "Literata",
     "Clause n → body → cite", "Contract excerpt",
     "Numbered clause with hanging indent — legal page geometry.",
     "ivory", "Policy · terms"),
    ("invoice_line", "Invoice Line", "content", "stack", "IBM Plex Mono",
     "Line items → total", "Invoice table",
     "Line-item table with a total lockup.",
     "paper", "Pricing detail"),
    ("checklist_run", "Run Checklist", "content", "stack", "DM Sans",
     "☐ → ☑ sequence", "Ops checklist",
     "Checkbox column; completion is the motion.",
     "snow", "Runbook"),
    ("glossary_term", "Glossary Term", "content", "split", "Fraunces",
     "Term | definition", "Dictionary split",
     "Giant term left, definition right.",
     "ivory", "Define · vocab"),
    # --- PPT / decks ---
    ("title_only", "Title Only", "ppt", "mega_type", "Inter",
     "One line. Sit.", "Keynote title slide",
     "Nothing but a balanced title. Empty space is the layout.",
     "snow", "Section · thesis"),
    ("section_break", "Section Break", "ppt", "chapters", "Oswald",
     "0n · chapter name", "Numbered act plate",
     "Huge chapter index + short name.",
     "midnight", "Act · module"),
    ("two_column_notes", "Two-column Notes", "ppt", "split", "Work Sans",
     "Claim | evidence", "Speaker-notes split",
     "Left claim, right evidence. Classic two-column, not Coral Split marketing.",
     "paper", "Briefing"),
    ("three_up", "Three-up", "ppt", "quad", "Poppins",
     "A · B · C equal cards", "Three equal beats",
     "Exactly three cards, equal width — not a bento mosaic.",
     "snow", "Pillars"),
    ("four_up", "Four-up", "ppt", "quad", "Manrope",
     "2×2 equal cells", "Quad grid",
     "Strict 2×2. No spanning hero cell (unlike Bento).",
     "paper", "Matrix"),
    ("quote_fullbleed", "Full-bleed Quote", "ppt", "quote", "Playfair Display",
     "Quote fills the frame", "Testimonial full bleed",
     "Quote is the slide; attribution in the corner.",
     "ivory", "Testimonial"),
    ("image_caption", "Image Caption", "ppt", "polaroid", "Inter",
     "Still → caption bar", "Figure with caption",
     "Media dominates; caption is a thin bar, not a bullet card.",
     "paper", "Figure · exhibit"),
    ("agenda_dots", "Agenda Dots", "ppt", "rail", "Barlow",
     "● ○ ○ ○ progress", "Dotted agenda",
     "Horizontal dots with the current stop filled.",
     "snow", "Workshop agenda"),
    ("swot_grid", "SWOT Grid", "ppt", "quad", "DM Sans",
     "S · W · O · T", "Classic SWOT",
     "Labeled 2×2 SWOT — strategy geometry.",
     "paper", "Strategy"),
    ("pest_grid", "PEST Grid", "ppt", "quad", "Barlow",
     "P · E · S · T", "Macro factors",
     "Four labeled macro cells.",
     "slate", "Context"),
    ("okr_cards", "OKR Cards", "ppt", "kanban", "Inter",
     "Objective → key results", "OKR stack",
     "One objective, three KR rows with scores.",
     "aurora", "Goals"),
    ("north_star", "North Star", "ppt", "kpi", "Sora",
     "One metric · one sentence", "North-star metric",
     "Single metric with a one-line why.",
     "midnight", "KPI story"),
    ("before_after", "Before / After", "ppt", "dual", "Poppins",
     "Before | After", "Split improvement",
     "Labeled before/after columns with a divider.",
     "emerald", "Change"),
    ("problem_solution", "Problem → Solution", "ppt", "dual", "Outfit",
     "Pain | fix", "Problem then fix",
     "Pain on the left, fix on the right — copy, not vs-bars.",
     "sunset", "Pitch"),
    ("cta_banner", "CTA Banner", "ppt", "poster", "Montserrat",
     "Offer → button plate", "Closing CTA",
     "Banner + button plate. End of deck.",
     "aurora", "Close"),
    ("speaker_notes_card", "Speaker Card", "ppt", "stack", "Figtree",
     "Title → 3 speaker lines", "Presenter card",
     "Sparse speaker card: title and three short lines max.",
     "snow", "Talk track"),
    # --- Teach ---
    ("socratic_q", "Socratic Q", "teach", "quote", "Fraunces",
     "Question only → wait", "Socratic pause",
     "The question is the slide. No answers yet.",
     "ivory", "Classroom"),
    ("analogy_bridge", "Analogy Bridge", "teach", "dual", "Nunito",
     "Familiar | new", "Bridge analogy",
     "Known world left, new idea right, arrow as the lesson.",
     "mint", "Intro concepts"),
    ("misconception", "Misconception", "teach", "dual", "Rubik",
     "Myth ✕ | fact ✓", "Wrong then right",
     "Struck-through myth vs fact. Proof Duo’s cousin with strike chrome.",
     "sunset", "Unlearn"),
    ("worked_example", "Worked Example", "teach", "chapters", "Inter",
     "Given → step → answer", "Worked problem",
     "Given, numbered working, boxed answer.",
     "paper", "Math · code"),
    ("check_your", "Check Your Work", "teach", "chalkboard", "Caveat",
     "Pause prompt → hint", "Pause card",
     "Handwritten pause prompt with a small hint chip.",
     "snow", "Practice"),
    ("recap_list", "Recap List", "teach", "stack", "DM Sans",
     "3 takeaways only", "Exit ticket",
     "Exactly three recap lines, numbered, then stop.",
     "paper", "Close"),
    ("formula_board", "Formula Board", "teach", "chalkboard", "JetBrains Mono",
     "Equation hero → legend", "Board equation",
     "Giant formula centered; legend under it.",
     "snow", "STEM"),
    ("proof_steps", "Proof Steps", "teach", "chapters", "Literata",
     "Assume → derive → QED", "Formal proof",
     "Numbered derivation with QED lockup.",
     "ivory", "Theory"),
    ("lab_setup", "Lab Setup", "teach", "kanban", "IBM Plex Mono",
     "Gear · env · command", "Setup triptych",
     "Three setup columns: gear, environment, first command.",
     "slate", "Tutorial start"),
    ("hint_ladder", "Hint Ladder", "teach", "funnel", "Outfit",
     "Vague → clearer → reveal", "Scaffolded hint",
     "Narrowing hints before the answer.",
     "mint", "Coaching"),
    ("peer_prompt", "Peer Prompt", "teach", "split", "Nunito",
     "You say | they try", "Pair activity",
     "Instructor prompt vs learner task.",
     "paper", "Workshop"),
    ("exit_ticket", "Exit Ticket", "teach", "poster", "Poppins",
     "One question to leave with", "Door question",
     "Single takeaway question as a poster.",
     "aurora", "Close"),
    # --- Story / film ---
    ("cold_open", "Cold Open", "story", "letterbox", "Anton",
     "Black → line → smash", "Trailer cold open",
     "Letterboxed one-liner, then smash cut.",
     "mono", "Open"),
    ("chapter_card", "Chapter Card", "story", "chapters", "Playfair Display",
     "Chapter n · title", "Novel chapter plate",
     "Literary chapter index, not a PPT section break (serif + ornament).",
     "ivory", "Acts"),
    ("vo_card", "VO Card", "story", "caption", "Newsreader",
     "Voiceover line only", "Narration card",
     "A single VO sentence, centered, no kicker.",
     "slate", "Narration"),
    ("freeze_frame", "Freeze Frame", "story", "polaroid", "Oswald",
     "Still → stamp caption", "Freeze + stamp",
     "Frozen still with a rubber-stamp caption.",
     "sunset", "Beat"),
    ("montage_grid", "Montage Grid", "story", "mosaic", "Syne",
     "6-up flashes", "Montage mosaic",
     "Six quick cells — montage, not bento feature tiles.",
     "nebula", "Time pass"),
    ("flashback", "Flashback", "story", "letterbox", "Literata",
     "Sepia plate → return", "Memory insert",
     "Inset letterbox with a date chip.",
     "ivory", "Memory"),
    ("epilogue", "Epilogue", "story", "magazine", "Playfair Display",
     "Quiet close → coda", "Coda page",
     "Quiet serif close, lots of margin.",
     "ivory", "End"),
    ("credits_roll", "Credits Roll", "story", "stack", "IBM Plex Mono",
     "Role — name column", "End credits",
     "Two-column credits, not bullets.",
     "mono", "Close"),
    ("sting_logo", "Sting Logo", "story", "poster", "Montserrat",
     "Silence → mark", "Producer sting",
     "Mark only. No headline.",
     "nebula", "Ident"),
    ("title_safe", "Title Safe", "story", "letterbox", "Barlow",
     "Name over picture", "On-picture title",
     "Lower title over implied picture with safe padding.",
     "midnight", "Film title"),
    ("act_wipe", "Act Wipe", "story", "split", "Oswald",
     "Act n wipes on", "Wipe between acts",
     "Hard vertical wipe carrying the act number.",
     "cyber", "Transition"),
    ("whisper_card", "Whisper Card", "story", "quote", "Fraunces",
     "Small italic line", "Intimate aside",
     "Tiny italic line in a large quiet field.",
     "ivory", "Aside"),
    # --- Tech / systems ---
    ("code_diff", "Code Diff", "tech", "dual", "JetBrains Mono",
     "− old | + new", "Unified diff",
     "Red/green diff columns — not a generic compare.",
     "slate", "Changelog · PR"),
    ("api_card", "API Card", "tech", "terminal", "IBM Plex Mono",
     "METHOD path → JSON", "Endpoint card",
     "HTTP method chip, path, and a JSON body.",
     "midnight", "API teach"),
    ("architecture_map", "Architecture Map", "tech", "subway", "Sora",
     "Edge → service → store", "Service map",
     "Named nodes on colored lines (arch diagram as transit).",
     "cyber", "Systems"),
    ("sequence_uml", "Sequence UML", "tech", "rail", "IBM Plex Mono",
     "Lifelines → messages", "Sequence sketch",
     "Vertical lifelines with message arrows.",
     "paper", "Protocol"),
    ("err_trace", "Error Trace", "tech", "terminal", "JetBrains Mono",
     "Stack frames top-down", "Stack trace",
     "Mono stack frames, highlight the failing line.",
     "slate", "Debug"),
    ("changelog_log", "Changelog", "tech", "stack", "Inter",
     "Added / fixed / breaking", "Keep-a-changelog",
     "Three labeled change groups.",
     "snow", "Release notes"),
    ("cli_prompt", "CLI Prompt", "tech", "terminal", "Space Mono",
     "$ command → stdout", "Shell lesson",
     "Prompt, command, stdout. Cursor blinks.",
     "mono", "CLI"),
    ("schema_table", "Schema Table", "tech", "stack", "IBM Plex Mono",
     "col · type · notes", "DB schema",
     "Column table, not bullets.",
     "paper", "Data model"),
    ("latency_heat", "Latency Heat", "tech", "mosaic", "IBM Plex Mono",
     "Heat cells of p99", "Heatmap tiles",
     "Cell intensity encodes latency.",
     "cyber", "Perf"),
    ("replica_set", "Replica Set", "tech", "cycle", "Manrope",
     "Primary ⇄ secondaries", "HA ring",
     "Primary + replicas on a ring.",
     "emerald", "Infra"),
    ("request_path", "Request Path", "tech", "rail", "Sora",
     "Client → edge → app → db", "Hop rail",
     "Labeled hops with timing chips.",
     "midnight", "Networking"),
    ("threat_model", "Threat Model", "tech", "quad", "Barlow",
     "Asset · threat · mit · residual", "STRIDE-ish quad",
     "Four security cells.",
     "slate", "Security"),
)


def _build_style(row: tuple[str, str, str, str, str, str, str, str, str, str]) -> dict:
    key, label, category, compose, font_label, template, example, description, _theme, uses = row
    stack = _FONTS.get(font_label, f"{font_label},Inter,system-ui,sans-serif")
    tok = dict(_COMPOSE_TOKENS.get(compose, _COMPOSE_TOKENS["stack"]))
    tok.update({
        "font": stack,
        "h2_font": stack,
        "motif": key,
        "layout_mode": compose,
        "h2_max_ch": "16ch" if compose in {"mega_type", "kinetic_center", "caption", "poster"} else "22ch",
        "body_max_ch": "28ch" if compose in {"split", "dual", "quad", "kanban"} else "38ch",
    })
    return {
        "key": key,
        "label": label,
        "category": category,
        "description": description,
        "example": example,
        "template": template,
        "motif": key,
        "font_label": font_label,
        "layout_mode": compose,
        "uses": uses,
        "story_arc": (
            f"{label.upper()} — {compose.replace('_', ' ')} geometry.\n"
            f"Sequence: {template}. Intended use: {uses}. "
            f"Do not flatten this into a generic three-bullet stack."
        ),
        "tokens": tok,
    }


EXTRA_VIDEO_STYLES: dict[str, dict] = {row[0]: _build_style(row) for row in _ROWS}
EXTRA_THEME_HINTS: dict[str, str] = {row[0]: row[8] for row in _ROWS}


COMPOSE_SLIDESHOW_CSS = r"""
  /* ---- Text fitting (all layouts) ---- */
  .scene, .body, .bullets li, .mx-card, .stat-card, .cmp-col, .hook, .quote {
    min-width: 0;
  }
  .stage-wrap { overflow: hidden; min-height: 0; }
  .scene { max-height: 100%; overflow: hidden; width: 100%; }
  .body.two { grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); }
  .body > :only-child { grid-column: 1 / -1; min-width: 0; width: 100%; max-width: 100%; }
  .compare, .hub, .quote, .matrix, .steps, .hook, .bars, .panel, .transform, .flow {
    width: 100%; max-width: 100%;
  }
  .slide h2, .b-text, .hook-punch, .hook-label, .mx-label, .mx-detail,
  .cap-text, .cmp-title, .quote p, .stat-label, .flow-label, .step-text {
    overflow-wrap: anywhere;
    word-break: break-word;
    hyphens: auto;
  }
  .slide h2 {
    text-wrap: balance;
    max-width: min(100%, var(--h2-max-ch, 20ch));
  }
  .b-text, .hook-punch, .mx-detail, .cap-text {
    text-wrap: pretty;
    max-width: min(100%, var(--body-max-ch, 38ch));
  }
  .b-text { flex: 1; min-width: 0; }
  .k-chip { max-width: min(70%, 28ch); }

  /* ---- Compose geometries ---- */
  body[data-compose="split"] .stage-wrap { align-items: stretch; }
  body[data-compose="split"] .scene { display: grid; width: min(1680px, 96vw); }
  body[data-compose="split"] .body.one:has(> :nth-child(2)),
  body[data-compose="split"] .body.stack:has(> :nth-child(2)) {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 36px;
  }
  body.vertical[data-compose="split"] .body.one,
  body.vertical[data-compose="split"] .body.stack { grid-template-columns: minmax(0, 1fr); }
  body[data-compose="split"] .slide h2 { max-width: 14ch; }

  body[data-compose="kinetic_center"] .scene { text-align: center; margin-inline: auto; }
  body[data-compose="kinetic_center"] .kicker { justify-content: center; }
  body[data-compose="kinetic_center"] .slide h2 {
    margin-inline: auto; max-width: 16ch;
    font-size: calc(clamp(36px, 5.2vw, 62px) * var(--h2-scale,1));
  }
  body[data-compose="kinetic_center"] .body { justify-items: center; }
  body[data-compose="kinetic_center"] .b-text { margin-inline: auto; }

  body[data-compose="lower_third"] .stage-wrap {
    align-items: flex-end; justify-content: flex-start; padding-bottom: 18%;
  }
  body[data-compose="lower_third"] .caption {
    left: 4%; right: auto; bottom: 7%; width: min(72%, 920px);
    border-radius: 0 14px 14px 0; border-left: 6px solid var(--a);
  }
  body[data-compose="lower_third"] .slide h2 { font-size: calc(42px * var(--h2-scale,.95)); max-width: 22ch; }

  body[data-compose="caption"] .scene { text-align: center; }
  body[data-compose="caption"] .kicker { display: none; }
  body[data-compose="caption"] .slide h2 {
    margin-inline: auto; font-size: calc(clamp(32px, 4.4vw, 52px) * var(--h2-scale,1)); max-width: 18ch;
  }
  body[data-compose="caption"] .caption {
    left: 8%; right: 8%; bottom: 10%; background: transparent; justify-content: center;
  }
  body[data-compose="caption"] .cap-text {
    font-size: clamp(18px, 2.6vw, 32px); font-weight: 700; text-align: center;
    max-width: 22ch; margin: 0 auto;
  }

  body[data-compose="kpi"] .stat-value { font-size: clamp(48px, 7vw, 96px); }
  body[data-compose="kpi"] .slide h2 { max-width: 18ch; font-size: calc(40px * var(--h2-scale,.9)); }

  body[data-compose="bento"] .matrix { grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); }
  body[data-compose="bento"] .mx-card:nth-child(1) { grid-row: span 2; min-height: 0; }
  body[data-compose="bento"] .slide h2 { max-width: 16ch; }
  body[data-compose="bento"] .v-bento .v-tile:nth-child(1) { min-height: min(240px, 32vh); }
  body[data-compose="kpi"] .v-agenda .v-num { font-size: 18px; width: 44px; height: 44px; }
  body[data-compose="rail"] .v-rail li { border-radius: 999px; text-align: center; align-items: center; }
  body[data-compose="kinetic_center"] .v-lead { margin-inline: auto; text-align: center; }
  body[data-compose="split"] .v-split { gap: 28px; }

  body[data-compose="rail"] .flow-horizontal,
  body[data-compose="rail"] .tut-steps {
    display: flex; flex-wrap: wrap; gap: 18px; justify-content: space-between;
  }
  body[data-compose="rail"] .flow-node { flex: 1 1 140px; border-radius: 999px; text-align: center; }

  body[data-compose="quote"] .scene { text-align: left; max-width: min(920px, 86vw); }
  body[data-compose="quote"] .kicker { opacity: .7; }
  body[data-compose="quote"] .quote p {
    font-size: clamp(28px, 4vw, 52px); line-height: 1.18; font-weight: 500; max-width: 22ch;
  }

  body[data-compose="letterbox"] .slide .bg::before,
  body[data-compose="letterbox"] .slide .bg::after {
    height: 9%; width: 100%; top: auto; right: auto; left: 0; border-radius: 0;
    background: #000; opacity: 1; filter: none;
  }
  body[data-compose="letterbox"] .slide .bg::before { top: 0; }
  body[data-compose="letterbox"] .slide .bg::after { bottom: 0; top: auto; }
  body[data-compose="letterbox"] .stage-wrap { padding: 10% 10% 14%; }
  body[data-compose="letterbox"] .slide h2 {
    letter-spacing: .06em; text-transform: uppercase; max-width: 16ch;
  }

  body[data-compose="chalkboard"] .slide .bg {
    background:
      radial-gradient(1200px 800px at 50% 40%, color-mix(in srgb, var(--panel) 40%, transparent), transparent),
      var(--bg);
  }
  body[data-compose="chalkboard"] .bullets li,
  body[data-compose="chalkboard"] .mx-card {
    background: transparent; box-shadow: none; border-style: dashed;
  }
  body[data-compose="chalkboard"] .slide h2 { font-weight: 600; max-width: 18ch; }

  body[data-compose="terminal"] .scene {
    font-variant-ligatures: none;
    background: color-mix(in srgb, var(--panel) 88%, #000);
    border: 1px solid var(--line); border-radius: 12px; padding: 28px 32px 36px;
  }
  body[data-compose="terminal"] .slide h2 {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: calc(36px * var(--h2-scale,.95)); max-width: 28ch;
  }
  body[data-compose="terminal"] .k-chip { font-size: 11px; }

  body[data-compose="magazine"] .scene { max-width: 1100px; }
  body[data-compose="magazine"] .slide h2 {
    font-size: calc(clamp(36px, 4.8vw, 58px) * var(--h2-scale,1)); max-width: 14ch; line-height: 1.05;
  }
  body[data-compose="magazine"] .body.one:has(> :nth-child(2)) { grid-template-columns: minmax(0, 1.1fr) minmax(0, .9fr); }
  body.vertical[data-compose="magazine"] .body.one { grid-template-columns: minmax(0, 1fr); }
  body[data-compose="magazine"] .b-text { font-size: 22px; font-weight: 500; max-width: 36ch; }

  body[data-compose="swiss"] .slide .bg::before { opacity: .9; background-size: 40px 40px; }
  body[data-compose="swiss"] .slide h2 {
    font-size: calc(clamp(40px, 5.4vw, 64px) * var(--h2-scale,1)); letter-spacing: -.07em; max-width: 12ch;
  }
  body[data-compose="swiss"] .bullets li,
  body[data-compose="swiss"] .mx-card { border-radius: 0; border-width: 2px; }

  body[data-compose="mega_type"] .kicker { display: none; }
  body[data-compose="mega_type"] .stage-wrap { padding: 8% 7% 14%; }
  body[data-compose="mega_type"] .slide h2 {
    font-size: calc(clamp(44px, 6.4vw, 78px) * var(--h2-scale,1)); line-height: .94; max-width: 12ch;
  }
  body[data-compose="mega_type"] .body { max-width: 22ch; }

  body[data-compose="dual"] .compare { gap: 0; }
  body[data-compose="dual"] .cmp-col {
    min-height: 0; padding: 28px; border-radius: 0;
  }
  body[data-compose="dual"] .cmp-col:first-child {
    border-right: 1px solid var(--line);
  }

  body[data-compose="mosaic"] .matrix {
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px;
  }
  body.vertical[data-compose="mosaic"] .matrix { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  body[data-compose="mosaic"] .mx-card { min-height: 0; }

  body[data-compose="cards_stack"] .mx-card,
  body[data-compose="cards_stack"] .bullets li {
    box-shadow: 10px 12px 0 color-mix(in srgb, var(--a) 22%, transparent);
  }
  body[data-compose="cards_stack"] .mx-card:nth-child(2) { transform: translate(8px, 8px); }
  body[data-compose="cards_stack"] .mx-card:nth-child(3) { transform: translate(16px, 16px); }

  body[data-compose="broadcast"] .caption {
    left: 0; right: 0; bottom: 0; border-radius: 0; height: auto; min-height: 12%; max-height: 22%;
    background: linear-gradient(90deg, var(--a), color-mix(in srgb, var(--a) 40%, #000));
  }
  body[data-compose="broadcast"] .cap-text { font-size: clamp(16px, 2vw, 24px); font-weight: 800; text-transform: uppercase; }
  body[data-compose="broadcast"] .brand-tag { top: 18px; }

  body[data-compose="device"] .scene {
    border: 10px solid color-mix(in srgb, var(--ink) 80%, #000);
    border-radius: 28px; padding: 36px 40px; max-width: 920px; margin: 0 auto;
    box-shadow: 0 40px 80px rgba(0,0,0,.35);
  }
  body[data-compose="device"] .slide h2 { max-width: 16ch; }

  body[data-compose="poster"] .stage-wrap { padding: 6% 8% 14%; }
  body[data-compose="poster"] .scene {
    border: 4px solid var(--ink); min-height: 0; max-height: 100%; padding: 36px 40px;
    display: flex; flex-direction: column; justify-content: space-between; overflow: hidden;
  }
  body[data-compose="poster"] .slide h2 {
    font-size: calc(clamp(40px, 5.6vw, 68px) * var(--h2-scale,1)); text-transform: uppercase; max-width: 10ch;
  }

  body[data-compose="ticker"] .caption {
    left: 0; right: 0; bottom: 0; height: 12%; border-radius: 0;
    overflow: hidden; white-space: nowrap;
  }
  body[data-compose="ticker"] .cap-text {
    font-size: 22px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
    max-width: none; animation: ticker-x 14s linear infinite;
  }
  @keyframes ticker-x { from { transform: translateX(8%); } to { transform: translateX(-60%); } }

  body[data-compose="chapters"] .k-chip::before {
    content: attr(data-ch);
  }
  body[data-compose="chapters"] .slide h2 { max-width: 14ch; }
  body[data-compose="chapters"] .tut-steps,
  body[data-compose="chapters"] .flow-horizontal { gap: 22px; }

  body[data-compose="glass"] .bullets li,
  body[data-compose="glass"] .mx-card, body[data-compose="glass"] .stat-card {
    background: color-mix(in srgb, var(--panel) 45%, transparent);
    backdrop-filter: blur(16px); border-radius: 28px;
  }
  body[data-compose="glass"] .k-chip, body[data-compose="glass"] .flow-node { border-radius: 999px; }

  body[data-compose="neon_sign"] .slide h2 {
    text-transform: uppercase; letter-spacing: .12em;
    text-shadow: 0 0 18px var(--a), 0 0 42px var(--b);
    max-width: 12ch;
  }
  body[data-compose="neon_sign"] .slide .bg::after { opacity: .55; }

  body[data-compose="blueprint"] .slide h2 {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    text-transform: uppercase; letter-spacing: .08em; font-size: calc(40px * var(--h2-scale,.95));
  }
  body[data-compose="blueprint"] .bullets li { border-radius: 0; border-style: dashed; }

  body[data-compose="funnel"] .bullets { align-items: center; }
  body[data-compose="funnel"] .bullets li:nth-child(1) { width: 100%; }
  body[data-compose="funnel"] .bullets li:nth-child(2) { width: 82%; }
  body[data-compose="funnel"] .bullets li:nth-child(3) { width: 64%; }
  body[data-compose="funnel"] .bullets li:nth-child(4) { width: 48%; }

  body[data-compose="cycle"] .flow-horizontal {
    display: flex; justify-content: center; gap: 28px; flex-wrap: wrap;
  }
  body[data-compose="cycle"] .flow-node {
    width: 160px; height: 160px; border-radius: 50%;
    display: grid; place-items: center; text-align: center;
  }

  body[data-compose="kanban"] .matrix,
  body[data-compose="kanban"] .body.one:has(> :nth-child(2)) {
    grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: start;
  }
  body.vertical[data-compose="kanban"] .matrix,
  body.vertical[data-compose="kanban"] .body.one { grid-template-columns: 1fr; }
  body[data-compose="kanban"] .mx-card { min-height: 200px; }

  body[data-compose="polaroid"] .mx-card, body[data-compose="polaroid"] .paper {
    background: #f8f4ea; color: #1a1a1a; border: 12px solid #f8f4ea;
    border-bottom-width: 48px; transform: rotate(-1.5deg);
  }
  body[data-compose="polaroid"] .mx-card:nth-child(2) { transform: rotate(2deg); }
  body[data-compose="polaroid"] .mx-label { color: #1a1a1a; }

  body[data-compose="filmstrip"] .body,
  body[data-compose="filmstrip"] .matrix {
    display: flex; gap: 10px; background: #111; padding: 18px 12px;
    border-block: 14px repeating-linear-gradient(90deg, #111 0 12px, #f4f4f5 12px 22px) solid #111;
  }
  body[data-compose="filmstrip"] .mx-card { flex: 1; min-width: 0; border-radius: 0; }

  body[data-compose="subway"] .flow-node {
    border-radius: 999px; border-width: 4px; min-width: 88px; text-align: center;
  }
  body[data-compose="subway"] .flow-horizontal { gap: 0; align-items: center; }
  body[data-compose="subway"] .flow-edge,
  body[data-compose="subway"] .vs-edge {
    height: 8px; flex: 1; background: var(--a); border-radius: 0;
  }

  body[data-compose="news_lower"] .caption {
    left: 0; right: 18%; bottom: 8%; border-radius: 0; height: auto;
    background: var(--a); padding: 14px 28px;
  }
  body[data-compose="news_lower"] .cap-text { color: #fff; font-weight: 800; text-transform: uppercase; max-width: 28ch; }
  body[data-compose="news_lower"] .slide h2 { max-width: 20ch; }

  body[data-compose="pip"] .scene { position: relative; }
  body[data-compose="pip"] .body.two { grid-template-columns: 1.6fr .7fr; }
  body[data-compose="pip"] .body.two > :last-child {
    border: 2px solid var(--a); border-radius: 16px; min-height: 200px;
  }

  body[data-compose="quad"] .matrix, body[data-compose="quad"] .stat-grid,
  body[data-compose="quad"] .body.one:has(> :nth-child(2)) {
    display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px;
  }
  body.vertical[data-compose="quad"] .matrix,
  body.vertical[data-compose="quad"] .body.one { grid-template-columns: 1fr; }
  body[data-compose="quad"] .mx-card { min-height: 180px; }

  body.vertical .slide h2 { max-width: min(100%, 14ch); }
  body.vertical .b-text { max-width: min(100%, 28ch); }

  /* ---- Remotion 2026 frames (geometry, not color) ---- */
  body[data-compose="audiogram"] .caption { left: 8%; right: 8%; bottom: 12%; }
  body[data-compose="audiogram"] .bullets { display:flex; gap:6px; align-items:flex-end; height:88px; }
  body[data-compose="audiogram"] .bullets li {
    flex:1; min-height:12px; height: calc(24px + var(--i) * 10px); padding:0; border:0;
    background: linear-gradient(180deg, var(--a), var(--b)); border-radius: 4px 4px 0 0;
  }
  body[data-compose="karaoke"] .b-text { font-size: clamp(28px, 4vw, 44px); font-weight:800; }
  body[data-compose="karaoke"] .bullets li { background:transparent; border:0; box-shadow:none; padding:4px 0; }
  body[data-compose="karaoke"] .bullets li:nth-child(1) .b-text { color:var(--a); }
  body[data-compose="scramble"] h2, body[data-compose="scramble"] .b-text {
    font-family:"IBM Plex Mono",ui-monospace,monospace; letter-spacing:.08em;
  }
  body[data-compose="counter_ring"] .stat-card {
    width: 220px; height:220px; border-radius:50%;
    background: conic-gradient(var(--a) 72%, color-mix(in srgb, var(--line) 40%, transparent) 0);
    display:flex; flex-direction:column; align-items:center; justify-content:center;
  }
  body[data-compose="code_hike"] .bullets li {
    font-family:"JetBrains Mono",ui-monospace,monospace; border-left:3px solid transparent;
  }
  body[data-compose="code_hike"] .bullets li:nth-child(2) { border-left-color: var(--a); background: color-mix(in srgb, var(--a) 12%, transparent); }
  body[data-compose="stargazer"] .stat-grid { display:flex; gap:12px; }
  body[data-compose="stargazer"] .stat-card { border-radius:999px; }
  body[data-compose="travel_map"] .slide .bg::before {
    background-image: radial-gradient(var(--a) 2px, transparent 2.5px);
    background-size: 48px 48px; opacity:.45;
  }
  body[data-compose="mask_reveal"] .slide h2 {
    clip-path: inset(0 0 0 0); animation: mot-clip .7s cubic-bezier(0.16,1,0.3,1) both;
  }
  body[data-compose="glitch_type"] h2 {
    text-shadow: 3px 0 var(--a), -3px 0 var(--b); letter-spacing:.04em;
  }
  body[data-compose="progress_track"] .bullets { gap:14px; }
  body[data-compose="progress_track"] .bullets li {
    height:18px; padding:0; border-radius:999px;
    background: color-mix(in srgb, var(--panel) 80%, transparent);
  }
  body[data-compose="word_cloud"] .bullets {
    display:flex; flex-wrap:wrap; gap:12px 18px; justify-content:center;
  }
  body[data-compose="word_cloud"] .bullets li {
    border-radius:999px; padding:8px 16px; width:auto;
  }
  body[data-compose="zoom_punch"] h2 { font-size: calc(84px * var(--h2-scale,1.2)); max-width: 12ch; }
  body[data-compose="safe_overlay"] .stage-wrap { padding: 12% 10% 18%; }
  body[data-compose="safe_overlay"] .slide .bg::before {
    border: 2px dashed color-mix(in srgb, var(--a) 45%, transparent);
    inset: 8%; background:none; opacity:1; mask:none; -webkit-mask:none;
  }
  body[data-compose="spring_cards"] .mx-card:nth-child(1) { transform: rotate(-4deg); }
  body[data-compose="spring_cards"] .mx-card:nth-child(2) { transform: rotate(3deg) translateY(12px); }
  body[data-compose="news_stack"] .caption {
    left:0; right:0; width:100%; border-radius:0; text-transform:uppercase;
  }
  body[data-compose="podcast_tile"] .body.one:has(> :nth-child(2)) { display:grid; grid-template-columns: 180px minmax(0, 1fr); gap:28px; }
  body[data-compose="repo_stars"] .stat-value::before { content:"★ "; color:var(--a); }
  body[data-compose="donut_stat"] .stat-card {
    border-radius:50%; width:200px; height:200px;
    background:
      radial-gradient(circle at 50% 50%, var(--bg) 54%, transparent 55%),
      conic-gradient(var(--a) 0 65%, var(--line) 0);
  }
  body[data-compose="light_leak"] .slide .bg::after {
    opacity:.55; filter:blur(50px); width:80%; height:50%; left:10%; top:-10%;
  }
  body[data-compose="particle_field"] .slide .bg::before {
    background-image: radial-gradient(circle, var(--a) 1.2px, transparent 1.6px);
    background-size: 22px 22px; opacity:.5;
  }
"""


def slideshow_compose_css() -> str:
    return COMPOSE_SLIDESHOW_CSS


GROUP_FONT_POOLS: dict[str, tuple[str, ...]] = {
    "teach": (
        "Caveat", "Nunito", "Literata", "Fraunces", "Rubik", "Baloo 2",
        "Fredoka", "Newsreader", "Figtree", "Outfit",
    ),
    "motion": (
        "Anton", "Oswald", "Syne", "Space Grotesk", "Sora",
        "Bricolage Grotesque", "Archivo", "Outfit", "Bebas Neue", "Kanit",
    ),
    "hyper": (
        "Playfair Display", "Instrument Serif", "Fraunces", "Newsreader",
        "Syne", "Bricolage Grotesque", "Literata", "Cormorant Garamond",
    ),
    "decks": (
        "Poppins", "Barlow", "Figtree", "Manrope", "Plus Jakarta Sans",
        "Work Sans", "Montserrat", "DM Sans", "Karla", "Lexend",
    ),
    "story": (
        "Playfair Display", "Literata", "Fraunces", "Newsreader",
        "Instrument Serif", "Oswald", "Anton", "Cormorant Garamond",
    ),
    "data": (
        "IBM Plex Mono", "DM Sans", "Manrope", "Montserrat", "Sora",
        "Barlow", "Outfit", "IBM Plex Sans", "Lexend", "Karla",
    ),
    "systems": (
        "JetBrains Mono", "IBM Plex Mono", "Space Mono", "Sora",
        "Barlow", "IBM Plex Sans", "Source Code Pro", "Archivo",
    ),
}

_KEEP_FONTS: dict[str, str] = {
    "whiteboard": "Caveat",
    "terminal": "JetBrains Mono",
    "blueprint": "IBM Plex Mono",
    "editorial": "Playfair Display",
    "documentary": "Literata",
}

# Extra stacks used by group assignment (merged into _FONTS at import).
_FONTS.update({
    "Bebas Neue": '"Bebas Neue",Oswald,Impact,sans-serif',
    "Kanit": "Kanit,Oswald,sans-serif",
    "Cormorant Garamond": '"Cormorant Garamond",Georgia,serif',
    "Karla": "Karla,Inter,sans-serif",
    "Lexend": "Lexend,Inter,sans-serif",
    "IBM Plex Sans": '"IBM Plex Sans",Inter,sans-serif',
    "Source Code Pro": '"Source Code Pro",ui-monospace,monospace',
})


def uniquify_layout_modes(styles: dict) -> None:
    """Each picker layout gets a globally unique HTML compose (not per-category)."""

    def _rank(k: str) -> tuple[int, int, int]:
        mode = str(styles[k].get("layout_mode") or "stack")
        named = 0 if k == mode else 1
        mapped = 0 if EXISTING_LAYOUT_MODES.get(k) == mode else 1
        return (named, mapped, 0 if k in FEATURED_LAYOUT_KEYS else 1)

    used: set[str] = set()
    for key in sorted(styles.keys(), key=_rank):
        spec = styles[key]
        mode = str(spec.get("layout_mode") or "stack")
        if mode not in used:
            used.add(mode)
            continue
        uniq = key if key not in used else f"u_{key}"
        spec["layout_mode"] = uniq
        tok = spec.get("tokens") or {}
        tok["layout_mode"] = uniq
        spec["tokens"] = tok
        used.add(uniq)


def assign_group_fonts(styles: dict) -> None:
    """Cycle distinctive faces inside each logical group so neighbors differ."""
    buckets: dict[str, list[str]] = {}
    for key, spec in styles.items():
        buckets.setdefault(str(spec.get("category") or "teach"), []).append(key)
    for cat, keys in buckets.items():
        pool = GROUP_FONT_POOLS.get(cat, GROUP_FONT_POOLS["decks"])
        i = 0
        for key in sorted(keys):
            font = _KEEP_FONTS.get(key) or pool[i % len(pool)]
            if key not in _KEEP_FONTS:
                i += 1
            stack = _FONTS.get(font, f"{font},Inter,system-ui,sans-serif")
            spec = styles[key]
            spec["font_label"] = font
            tok = spec.get("tokens") or {}
            tok["font"] = stack
            tok["h2_font"] = stack
            spec["tokens"] = tok


def generated_compose_css(styles: dict | None = None) -> str:
    """Unique geometry CSS for compose ids that are not in the hand-written set."""
    import hashlib

    cols_opts = (
        "1fr", "1fr 1fr", "1.4fr .85fr", ".85fr 1.4fr", "1fr 1fr 1fr",
        "2fr 1fr", "1fr 2fr", "168px 1fr", "1fr 168px", "1fr 1fr 1fr 1fr",
    )
    parts = ["  /* Generated unique frames (one compose per layout) */"]
    seen: set[str] = set()
    for spec in (styles or {}).values():
        mode = str(spec.get("layout_mode") or "")
        if not mode or mode in COMPOSE_MODES or mode in seen:
            continue
        seen.add(mode)
        n = int(hashlib.md5(mode.encode("utf-8")).hexdigest()[:8], 16)
        cols = cols_opts[n % 10]
        align = ("left", "center", "start")[(n // 10) % 3]
        h2 = (48, 56, 64, 72, 40, 84, 52, 60)[(n // 30) % 8]
        radius = ("0px", "6px", "12px", "20px", "28px", "999px")[(n // 8) % 6]
        widget = n % 12
        extras = (
            f'body[data-compose="{mode}"] .body.one {{ display:flex; flex-direction:column; gap:18px; }}',
            f'body[data-compose="{mode}"] .bullets {{ display:flex; flex-wrap:wrap; gap:12px; }}'
            f' body[data-compose="{mode}"] .bullets li {{ width:auto; border-radius:999px; padding:10px 18px; }}',
            f'body[data-compose="{mode}"] .body.one:has(> :nth-child(2)) {{ display:grid; grid-template-columns:{cols}; gap:28px; }}',
            f'body[data-compose="{mode}"] .stat-card {{ border-radius:50%; width:200px; height:200px; }}',
            f'body[data-compose="{mode}"] h2, body[data-compose="{mode}"] .b-text {{ font-variant-ligatures:none; letter-spacing:.02em; }}',
            f'body[data-compose="{mode}"] .caption {{ left:0; right:18%; bottom:8%; border-radius:0; }}',
            f'body[data-compose="{mode}"] .stage-wrap {{ padding:12% 10% 16%; }}',
            f'body[data-compose="{mode}"] .scene {{ text-align:center; }}'
            f' body[data-compose="{mode}"] .slide h2 {{ max-width:12ch; margin-inline:auto; }}',
            f'body[data-compose="{mode}"] .quote p {{ font-style:italic; }}',
            f'body[data-compose="{mode}"] .flow-horizontal {{ display:flex; gap:12px; }}',
            f'body[data-compose="{mode}"] .bullets {{ display:flex; gap:6px; align-items:flex-end; height:80px; }}'
            f' body[data-compose="{mode}"] .bullets li {{ flex:1; padding:0; min-height:12px; height:calc(16px + var(--i)*12px); }}',
            f'body[data-compose="{mode}"] .body.one:has(> :nth-child(2)) {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }}',
        )
        parts.append(
            f'  body[data-compose="{mode}"] .scene {{ text-align:{align}; }}\n'
            f'  body[data-compose="{mode}"] .slide h2 {{'
            f' font-size:calc({h2}px * var(--h2-scale,1)); }}\n'
            f'  body[data-compose="{mode}"] .bullets li,'
            f' body[data-compose="{mode}"] .mx-card {{ border-radius:{radius}; }}\n'
            f'  {extras[widget]}'
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Grouping, curated colors, exclusive chrome (no shared slide frames)
# ---------------------------------------------------------------------------

STYLE_GROUP_LABELS: dict[str, str] = {
    "teach": "Teach",
    "motion": "Motion",
    "hyper": "HyperFrames",
    "decks": "Decks",
    "story": "Story",
    "data": "Data",
    "systems": "Code",
}

CATEGORY_REMAP: dict[str, str] = {
    "hybrid": "teach",
    "ppt": "decks",
    "modern_ppt": "decks",
    "content": "data",
    "tech": "systems",
}

CATEGORY_KEY_OVERRIDES: dict[str, str] = {
    "hybrid": "teach",
    "hybrid_kinetic": "motion",
    "hybrid_data": "data",
    "hybrid_story": "story",
}

# Curated palettes (old keys still resolve via aliases). The first six are the
# originals; the rest are the added light and dark options.
CURATED_THEME_KEYS: tuple[str, ...] = (
    "aurora", "midnight", "sunset", "snow", "emerald", "cyber",
    "ocean", "forest", "rose", "citrus", "grape", "graphite", "sand", "sky",
)
THEME_ALIASES: dict[str, str] = {
    "paper": "snow",
    "ivory": "snow",
    "mint": "snow",
    "nebula": "aurora",
    "slate": "midnight",
    "mono": "midnight",
}

_CAPTIONS = ("bar", "left", "pill", "hidden", "tick")
_ALIGNS = ("left", "center", "start")
_KICKERS = ("left", "center", "hidden", "chip")
_MOTIONS = ("clip", "rise", "scale", "wipe", "blur")
_ORNS = ("rail", "marks", "dots", "band", "none")


def remap_category(style_key: str, category: str) -> str:
    if style_key in CATEGORY_KEY_OVERRIDES:
        return CATEGORY_KEY_OVERRIDES[style_key]
    return CATEGORY_REMAP.get(category, category if category in STYLE_GROUP_LABELS else "teach")


def alias_theme(theme_key: str | None) -> str:
    raw = (theme_key or "").strip().lower()
    return THEME_ALIASES.get(raw, raw)


def _combo_from_n(n: int) -> tuple[str, str, str, str, str]:
    return (
        _CAPTIONS[n % len(_CAPTIONS)],
        _ALIGNS[(n // 5) % len(_ALIGNS)],
        _KICKERS[(n // 15) % len(_KICKERS)],
        _MOTIONS[(n // 60) % len(_MOTIONS)],
        _ORNS[(n // 300) % len(_ORNS)],
    )


def chrome_for(style_key: str, used: set[tuple] | None = None) -> dict[str, str]:
    """Exclusive caption/align/kicker/motion/ornament for this layout key."""
    import hashlib
    h = int(hashlib.md5(style_key.encode("utf-8")).hexdigest()[:10], 16)
    n = h
    combo = _combo_from_n(n)
    if used is not None:
        while combo in used:
            n += 1
            combo = _combo_from_n(n)
        used.add(combo)
    cap, align, kicker, motion, orn = combo
    return {
        "chrome_caption": cap,
        "chrome_align": align,
        "chrome_kicker": kicker,
        "chrome_motion": motion,
        "chrome_orn": orn,
    }


MOTION_SLIDESHOW_CSS = r"""
  /* 2026 motion: expo-out entrances, clip-path wipes, transform/opacity only. */
  :root {
    --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
    --ease-spring: linear(0, 0.5 20%, 1.04 55%, 0.98 75%, 1);
  }
  .slide.active .kicker { animation: none; }
  .slide.active h2 { animation: none; }
  .slide.active .device { animation: none; }
  .slide.active .bullets li { animation: none; }
  .slide.active .b-mark { animation: none; }
  .slide.active .caption { animation: none; }
  .slide.active .bg { animation: ken-soft 16s var(--ease-out-expo) both; }
  .slide.active .bg::before { animation: none; }

  body[data-motion="rise"] .slide.active h2 {
    animation: mot-rise .55s var(--ease-out-expo) both;
  }
  body[data-motion="rise"] .slide.active .kicker {
    animation: mot-rise .4s var(--ease-out-expo) both;
  }
  body[data-motion="clip"] .slide.active h2 {
    animation: mot-clip .65s var(--ease-out-expo) both;
  }
  body[data-motion="clip"] .slide.active .kicker {
    animation: mot-clip .45s var(--ease-out-expo) both;
  }
  body[data-motion="scale"] .slide.active h2 {
    animation: mot-scale .55s var(--ease-spring) both;
  }
  body[data-motion="wipe"] .slide.active h2 {
    animation: mot-wipe .7s var(--ease-out-expo) both;
  }
  body[data-motion="blur"] .slide.active h2 {
    animation: mot-blur .6s var(--ease-out-expo) both;
  }
  body[data-motion="rise"] .slide.active .bullets li,
  body[data-motion="clip"] .slide.active .bullets li,
  body[data-motion="scale"] .slide.active .bullets li,
  body[data-motion="wipe"] .slide.active .bullets li,
  body[data-motion="blur"] .slide.active .bullets li {
    animation: mot-rise .5s var(--ease-out-expo) both;
    animation-delay: calc(.12s + var(--i, 1) * .05s);
  }
  body[data-motion] .slide.active .caption {
    animation: mot-rise .45s var(--ease-out-expo) .18s both;
  }

  @keyframes mot-rise { from { opacity:0; transform:translateY(18px); } to { opacity:1; transform:none; } }
  @keyframes mot-clip {
    from { opacity:0; clip-path: inset(0 100% 0 0); }
    to { opacity:1; clip-path: inset(0 0 0 0); }
  }
  @keyframes mot-scale { from { opacity:0; transform:scale(.94); } to { opacity:1; transform:none; } }
  @keyframes mot-wipe {
    from { opacity:0; clip-path: inset(100% 0 0 0); }
    to { opacity:1; clip-path: inset(0 0 0 0); }
  }
  @keyframes mot-blur { from { opacity:0; filter:blur(12px); transform:translateY(10px); } to { opacity:1; filter:blur(0); transform:none; } }
  @keyframes ken-soft { from { transform:scale(1.04); } to { transform:scale(1); } }

  body[data-align="center"] .scene { text-align:center; margin-inline:auto; }
  body[data-align="center"] .kicker { justify-content:center; }
  body[data-align="center"] .slide h2 { margin-inline:auto; }
  body[data-align="start"] .scene { text-align:left; }
  body[data-kicker="hidden"] .kicker { display:none; }
  body[data-kicker="center"] .kicker { justify-content:center; }
  body[data-kicker="chip"] .k-chip { border-radius:999px; }

  body[data-caption="hidden"] .caption { display:none; }
  body[data-caption="left"] .caption { left:4%; right:auto; transform:none; width:min(56%, 720px); }
  body[data-caption="pill"] .caption { border-radius:999px; padding:10px 28px; }
  body[data-caption="tick"] .caption { border-radius:0; border-left:0; border-top:3px solid var(--a); }
  body[data-caption="bar"] .caption { left:0; right:0; width:100%; border-radius:0; }

  .frame-orn { pointer-events:none; position:absolute; inset:0; z-index:1; }
  body[data-orn="rail"] .frame-orn::before {
    content:""; position:absolute; left:0; top:0; bottom:0; width:10px; background:var(--a);
  }
  body[data-orn="band"] .frame-orn::before {
    content:""; position:absolute; left:0; right:0; top:0; height:8px;
    background:linear-gradient(90deg, var(--a), var(--b));
  }
  body[data-orn="marks"] .frame-orn::before,
  body[data-orn="marks"] .frame-orn::after {
    content:""; position:absolute; width:18px; height:18px;
    border:2px solid var(--a);
  }
  body[data-orn="marks"] .frame-orn::before { top:16px; left:16px; border-right:0; border-bottom:0; }
  body[data-orn="marks"] .frame-orn::after { bottom:16px; right:16px; border-left:0; border-top:0; }
  body[data-orn="dots"] .frame-orn::before {
    content:""; position:absolute; top:18px; right:22px; width:10px; height:10px;
    border-radius:50%; background:var(--a); box-shadow:0 18px 0 var(--b), 0 36px 0 var(--a);
  }
  body[data-orn="none"] .frame-orn { display:none; }
"""


def unique_slideshow_css(styles: dict | None = None) -> str:
    """Motion + exclusive chrome. Frame recipes live on body data-* attrs."""
    return MOTION_SLIDESHOW_CSS


def motion_slideshow_css() -> str:
    return MOTION_SLIDESHOW_CSS
