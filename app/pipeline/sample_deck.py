"""Sample lesson used by the style picker preview.

The Admin "Visual styles" stage and the Studio picker render this deck through
the same ``render_slideshow_html`` the real pipeline uses, so what a teacher sees
in the picker is exactly what the video will look like.
"""
from __future__ import annotations

import copy

SAMPLE_MODEL = {"title":"How Photosynthesis Works","slides":[
 {"heading":"How plants turn light into food","layout":"cover","bullets":["Sunlight in, sugar out","Happens inside the chloroplast","Powers almost all life on Earth"],"narration":"Every leaf on your desk is quietly running a tiny solar factory. Let's see how it works."},
 {"heading":"The two stages","layout":"steps","steps":["Light reactions capture energy in the thylakoid","The Calvin cycle builds glucose from CO2","Oxygen is released as a by-product"],"narration":"Think of it as charging a battery, then cooking with it."},
 {"heading":"Inputs vs outputs","layout":"compare","compare":{"left_title":"Goes in","left":["Sunlight","Water","Carbon dioxide"],"right_title":"Comes out","right":["Glucose","Oxygen"]},"narration":"Three things go in. Two come out."},
 {"heading":"Why it matters","layout":"stat","stats":[{"value":"21%","label":"of air is oxygen"},{"value":"100B","label":"tons carbon fixed / yr"}],"narration":"That small leaf chemistry shapes the air we breathe."},
 {"heading":"Remember this","layout":"bullets","bullets":["Light energy becomes chemical energy","Chloroplasts are the site","CO2 + H2O + light -> glucose + O2"],"narration":"If you remember one line, remember the equation."},
 {"heading":"A long heading that goes on and on to test how wrapping behaves in the title area","layout":"bullets","bullets":["Chlorophyll absorbs mostly red and blue light, which is why leaves look green to our eyes and not black","The thylakoid membrane holds the protein complexes that split water and pump protons across","ATP synthase turns the proton gradient into ATP, the cell's short term energy currency","The Calvin cycle then uses that ATP and NADPH to fix carbon dioxide into three carbon sugars","Rubisco is the enzyme that does the fixing and it is slow, so plants make a lot of it","Oxygen leaves through the stomata, tiny pores that also let water vapour escape"],"narration":"A deliberately long slide to test shrink to fit behaviour in the body area of the frame."},
 {"heading":"Light vs dark reactions","layout":"matrix","matrix":{"items":[{"label":"Light reactions","detail":"Thylakoid membrane, makes ATP + NADPH"},{"label":"Calvin cycle","detail":"Stroma, fixes CO2 into sugar"},{"label":"Photosystem II","detail":"Splits water, releases O2"},{"label":"Photosystem I","detail":"Re-energises electrons for NADPH"}]},"narration":"Four parts to keep straight."},
]}

SAMPLE_LABELS = ["Cover", "Steps", "Compare", "Stats", "Bullets", "Dense", "Matrix"]


def render_sample(style: str, theme: str, video_format: str = "youtube_video") -> str:
    from . import content

    if (style or "").strip().lower() in ("", "auto"):
        style = "whiteboard"
    if (theme or "").strip().lower() in ("", "auto"):
        theme = "snow"
    opts = {"video_style": style, "video_theme": theme,
            "video_format": video_format or "youtube_video"}
    return content.render_slideshow_html(copy.deepcopy(SAMPLE_MODEL), opts)
