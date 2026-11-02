"""Template-free slide layout synthesizer.

Instead of picking one of N fixed CSS templates and recolouring it, this module
*computes* a layout from the data on every slide:

* item count, text length, optional weights and numeric values decide how much
  area each item gets (squarified treemap, weighted skyline, golden splits …);
* a per-slide seed decides the free parameters (split order, mirroring, ring
  phase, slant, jitter) so no two slides share geometry;
* text is fitted to each computed cell (binary-search style, like Pretext /
  ggfittext), with a browser-side guard that shrinks anything still clipped;
* motion is per-family (fly-from-centre, orbit spin, drop, unfold, grow-up …)
  and uses only transform / opacity / stroke-dashoffset so it stays seek-safe
  for the frame-driven capture timeline.

Techniques borrowed from current practice: squarified treemaps (Bruls et al.),
arithmetic text measurement (Pretext), constraint-based "smart slide"
guardrails (Beautiful.ai), and HyperFrames' seek-safe animation rules.

Uniqueness is enforced at two levels:

* per deck: :func:`synthesize` refuses a (family, geometry signature) already
  used by another slide, retrying with new seeds / another family;
* per template: :func:`template_profile` maps every template key to a unique
  (family order, background motif, heading treatment) fingerprint.
"""
from __future__ import annotations

import hashlib
import html
import math
import random
import re
from collections import Counter
from dataclasses import dataclass, field

FAMILIES: tuple[str, ...] = (
    "treemap", "orbit", "cascade", "masonry", "path",
    "golden", "bands", "scatter", "slices", "skyline",
)
MOTIFS: tuple[str, ...] = ("none", "dots", "rings", "diag", "grid", "waves", "cross")
HTYPES: tuple[str, ...] = ("plain", "bar", "sweep", "caps", "marker", "offset")

# Item counts each family can present legibly.
_FIT: dict[str, tuple[int, int]] = {
    "treemap": (2, 8), "orbit": (3, 7), "cascade": (2, 6), "masonry": (3, 8),
    "path": (3, 6), "golden": (2, 5), "bands": (2, 7), "scatter": (2, 7),
    "slices": (2, 6), "skyline": (2, 7),
}
# Families whose reading order matters (steps) vs magnitude families (stats).
_ORDERED = ("cascade", "path", "bands", "slices", "orbit")
_KIND_FAMILIES: dict[str, tuple[str, ...]] = {
    "bullets": FAMILIES,
    "steps": _ORDERED,
    "stats": ("treemap", "skyline", "orbit", "masonry", "scatter", "golden", "slices", "bands"),
    "matrix": ("treemap", "orbit", "masonry", "scatter", "golden", "slices", "bands", "skyline"),
}


@dataclass
class Item:
    text: str
    detail: str = ""
    value: str = ""
    weight: float = 1.0
    n: int = 1


@dataclass
class Cell:
    x: float
    y: float
    w: float
    h: float
    rot: float = 0.0
    clip: str = ""
    order: int = 0
    dx: float = 0.0        # entrance offset, % of host box
    dy: float = 0.0
    s0: float = 0.85
    sx0: float | None = None
    sy0: float | None = None
    r0: float = 0.0
    ease: str = "outCubic"
    origin: str = "50% 50%"
    inner: float = 1.0     # usable fraction of the box for text (ellipses etc.)
    pad: float = 16.0
    alt: bool = False
    lead: bool = False
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# seeds / helpers
# ---------------------------------------------------------------------------
def _h(s: str) -> int:
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:12], 16)


def _rng(seed: str) -> random.Random:
    return random.Random(_h(seed))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _num(s: str) -> float | None:
    m = re.search(r"-?\d[\d,]*\.?\d*", str(s or ""))
    if not m:
        return None
    try:
        v = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    t = str(s).lower()
    if re.search(r"\d\s*(k|thousand)\b", t):
        v *= 1e3
    elif re.search(r"\d\s*(m|million)\b", t):
        v *= 1e6
    elif re.search(r"\d\s*(b|billion)\b", t):
        v *= 1e9
    return abs(v)


def make_items(
    texts: list,
    *,
    weights: list | None = None,
    details: list | None = None,
    values: list | None = None,
) -> list[Item]:
    """Normalise raw strings into :class:`Item` with data-driven weights."""
    out: list[Item] = []
    for i, t in enumerate(texts):
        text = str(t or "").strip()
        if not text:
            continue
        w = None
        if weights and i < len(weights):
            try:
                w = float(weights[i])
            except (TypeError, ValueError):
                w = None
            if w is not None and not math.isfinite(w):
                w = None
        val = str(values[i]).strip() if values and i < len(values) and values[i] else ""
        if w is None and val:
            nv = _num(val)
            if nv is not None:
                w = 1.0 + math.log10(1.0 + nv) * 0.55
        if w is None:
            w = 1.0 + min(len(text), 90) / 60.0
        det = str(details[i]).strip() if details and i < len(details) and details[i] else ""
        out.append(Item(text=text, detail=det, value=val, weight=_clamp(w, 0.6, 3.2), n=len(out) + 1))
    return out


def derive_items(narration: str, limit: int = 5) -> list[str]:
    """Pull short key phrases from narration when a slide has no bullets."""
    text = re.sub(r"\s+", " ", str(narration or "")).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?;])\s+", text)
    out: list[str] = []
    for p in parts:
        p = p.strip(" .!?;,-")
        if len(p) < 8:
            continue
        words = p.split()
        if len(words) > 11:
            p = " ".join(words[:11]).rstrip(",:;") + "…"
        out.append(p)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# text fitting (arithmetic, no DOM)
# ---------------------------------------------------------------------------
_CHAR_W = 0.56   # average glyph width in em (conservative for bold sans)
_LINE_H = 1.22


def _lines_needed(text: str, fs: float, width: float) -> int:
    maxc = max(1, int(width / (fs * _CHAR_W)))
    lines, cur = 1, 0
    for word in text.split():
        ln = len(word)
        while ln > maxc:
            if cur:
                lines += 1
                cur = 0
            lines += 1
            ln -= maxc
        if cur == 0:
            cur = ln
        elif cur + 1 + ln <= maxc:
            cur += 1 + ln
        else:
            lines += 1
            cur = ln
    return lines


def fit_font(text: str, width: float, height: float, lo: int = 15, hi: int = 52, extra_h: float = 0.0) -> int:
    """Largest font size (px) whose wrapped text fits width × height."""
    if width <= 0 or height <= 0:
        return lo
    for fs in range(int(hi), int(lo) - 1, -1):
        if _lines_needed(text, fs, width) * fs * _LINE_H + extra_h <= height:
            return fs
    return int(lo)


# ---------------------------------------------------------------------------
# geometry families (all return list[Cell] in the W×H pixel box)
# ---------------------------------------------------------------------------
def _squarify(sizes: list[float], x: float, y: float, dx: float, dy: float) -> list[tuple[float, float, float, float]]:
    def worst(row: list[float], side: float) -> float:
        s = sum(row)
        return max(max(side * side * r / (s * s), (s * s) / (side * side * r)) for r in row)

    sizes = [a for a in sizes if a > 0]
    out: list[tuple[float, float, float, float]] = []
    while sizes:
        if dx <= 1 or dy <= 1:
            # Leftover sliver: split it instead of dividing by a zero side.
            if dx >= dy:
                cw = max(dx, 1.0) / len(sizes)
                for k, _a in enumerate(sizes):
                    out.append((x + cw * k, y, cw, max(dy, 1.0)))
            else:
                rh = max(dy, 1.0) / len(sizes)
                for k, _a in enumerate(sizes):
                    out.append((x, y + rh * k, max(dx, 1.0), rh))
            break
        side = min(dx, dy)
        row = [sizes[0]]
        i = 1
        while i < len(sizes) and worst(row + [sizes[i]], side) <= worst(row, side):
            row.append(sizes[i])
            i += 1
        s = sum(row)
        if dx >= dy:
            cw = s / dy
            cy = y
            for a in row:
                ch = a / cw
                out.append((x, cy, cw, ch))
                cy += ch
            x += cw
            dx -= cw
        else:
            rh = s / dx
            cx = x
            for a in row:
                cw = a / rh
                out.append((cx, y, cw, rh))
                cx += cw
            y += rh
            dy -= rh
        sizes = sizes[i:]
    return out


def _fam_treemap(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    ws = [_clamp(it.weight, 1.0, 2.8) ** 1.5 for it in items]
    ws[0] *= r.choice((1.3, 1.6, 1.9))
    order = sorted(range(n), key=lambda i: -ws[i])
    tot = sum(ws)
    sizes = [ws[i] / tot * W * H for i in order]
    rects = _squarify(sizes, 0, 0, W, H)
    fx, fy = r.random() < 0.5, r.random() < 0.5
    gap = r.choice((8, 10, 14, 18))
    cells: list[Cell | None] = [None] * n
    for rank, i in enumerate(order):
        x, y, w, h = rects[rank]
        if fx:
            x = W - x - w
        if fy:
            y = H - y - h
        cx, cy = x + w / 2, y + h / 2
        cells[i] = Cell(
            x + gap / 2, y + gap / 2, w - gap, h - gap, order=rank,
            dx=(W / 2 - cx) / W * 100, dy=(H / 2 - cy) / H * 100,
            s0=0.25, ease="outExpo", lead=rank == 0, pad=18,
        )
    return [c for c in cells if c], {"gap": gap, "fx": fx, "fy": fy}


def _fam_orbit(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    k = n - 1
    a0 = r.uniform(0, 2 * math.pi)
    direction = r.choice((1, -1))
    cx, cy = W / 2, H / 2
    scale = 1.0
    cells: list[Cell] = []
    pts: list[tuple[float, float]] = []
    for _ in range(9):
        sw = W * (0.25 if k <= 4 else 0.21) * scale
        sh = H * (0.31 if k <= 4 else 0.27) * scale
        lw, lh = W * 0.30 * scale, H * 0.36 * scale
        rx = W / 2 - sw / 2 - 6
        ry = H / 2 - sh / 2 - 6
        cells = [Cell(cx - lw / 2, cy - lh / 2, lw, lh, order=0, s0=0.3, ease="outBack",
                      lead=True, inner=0.74, pad=10)]
        pts = []
        for j in range(k):
            ang = a0 + direction * j * 2 * math.pi / k
            px, py = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
            pts.append((px, py))
            cells.append(Cell(
                px - sw / 2, py - sh / 2, sw, sh, order=j + 1,
                dx=(cx - px) / W * 100, dy=(cy - py) / H * 100,
                s0=0.2, r0=-140 * direction, ease="outBack", inner=0.74, pad=8,
            ))
        if check_cells("orbit", cells, W, H, tol=0.0):
            break
        scale *= 0.92
    return cells, {"spokes": [(cx, cy, px, py) for px, py in pts], "a0": round(a0, 2)}


def _fam_cascade(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    mode = r.choice(("stair", "stairr", "zig", "fan", "fanr", "vee"))
    step = min(r.choice((0.04, 0.06, 0.08, 0.10)) * W, 0.26 * W / max(1, n - 1))
    if mode == "zig":
        off = r.choice((0.07, 0.10, 0.13)) * W
        offs = [off * (i % 2) for i in range(n)]
    elif mode == "stair":
        offs = [step * i for i in range(n)]
    elif mode == "stairr":
        offs = [step * (n - 1 - i) for i in range(n)]
    elif mode in ("fan", "fanr"):
        amp = min(0.12 * W, step * 1.6 * (n - 1) / 2 + 20)
        offs = [amp * math.sin(math.pi * i / max(1, n - 1)) * (1 if mode == "fan" else -1) + (0 if mode == "fan" else amp)
                for i in range(n)]
    else:  # vee: indent grows toward the middle
        mid = (n - 1) / 2
        offs = [step * (mid - abs(i - mid)) * 1.4 for i in range(n)]
    offs = [max(0.0, v) for v in offs]
    weighted = r.random() < 0.5
    ws = [_clamp(it.weight, 1.0, 2.0) for it in items] if weighted else [1.0] * n
    gap = r.choice((8, 12, 16))
    avail = H - gap * (n - 1)
    cw = W - max(offs)
    y = 0.0
    cells = []
    for i in range(n):
        ch = avail * ws[i] / sum(ws)
        side = -1 if (offs[i] <= max(offs) / 2) else 1
        cells.append(Cell(
            offs[i], y, cw, ch, order=i,
            dx=side * 26, s0=0.94, ease="outBack", lead=i == 0, pad=18,
        ))
        y += ch + gap
    return cells, {"mode": mode, "weighted": weighted, "gap": gap}


def _fam_masonry(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    landscape = W >= H
    lead_row = n >= 5 and r.random() < 0.5
    gap = r.choice((10, 14, 18))
    body = items[1:] if lead_row else items
    m = len(body)
    lead_h = H * r.choice((0.24, 0.30, 0.36)) if lead_row else 0.0
    top = lead_h + (gap if lead_row else 0)
    cols = 3 if (landscape and m >= 4) else 2
    if m == 3 and landscape and r.random() < 0.5:
        cols = 3
    ratios = r.choice((
        (1, 1, 1), (1.45, 1, 1), (1, 1.45, 1), (1, 1, 1.45), (1.7, 1, 1.2), (1, 1.7, 1.2),
        (1.2, 1, 1.7), (1.3, 1.3, 1),
    ))[:cols]
    heights = [1.0 + len(it.text) / 34.0 + 0.4 * (it.weight - 1) for it in body]
    col_items: list[list[int]] = [[] for _ in range(cols)]
    col_load = [0.0] * cols
    for i in range(m):
        j = min(range(cols), key=lambda c: (col_load[c], c))
        col_items[j].append(i)
        col_load[j] += heights[i]
    used = [c for c in range(cols) if col_items[c]]
    rs = [ratios[c] for c in used]
    total_w = W - gap * (len(used) - 1)
    out: dict[int, Cell] = {}
    x = 0.0
    rank = 1 if lead_row else 0
    if lead_row:
        out[0] = Cell(0, 0, W, lead_h, order=0, dy=-26, s0=0.96, ease="outCubic", lead=True, pad=18)
    for ui, c in enumerate(used):
        cw = total_w * rs[ui] / sum(rs)
        idxs = col_items[c]
        hs = [heights[i] for i in idxs]
        avail = H - top - gap * (len(idxs) - 1)
        y = top
        for i, hh in zip(idxs, hs):
            ch = avail * hh / sum(hs)
            gi = i + (1 if lead_row else 0)
            out[gi] = Cell(x, y, cw, ch, order=rank, dy=-26, s0=0.96, ease="outCubic",
                           lead=(rank == 0), pad=16)
            rank += 1
            y += ch + gap
        x += cw + gap
    cells = [out[i] for i in range(n)]
    return cells, {"cols": len(used), "ratios": [round(v, 2) for v in rs], "lead_row": lead_row}


def _smooth_path(pts: list[tuple[float, float]]) -> str:
    if len(pts) < 2:
        return ""
    d = [f"M{pts[0][0]:.2f},{pts[0][1]:.2f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else pts[i + 1]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {p2[0]:.2f},{p2[1]:.2f}")
    return " ".join(d)


def _fam_path(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    vertical = H > W
    Wv, Hv = (H, W) if vertical else (W, H)
    amp = r.uniform(0.015, 0.05) * Hv
    freq = r.choice((0.75, 1.0, 1.5))
    phase = r.uniform(0, 2 * math.pi)
    first_up = r.random() < 0.5
    lab_h = 0.40 * Hv
    lab_w = min(2 * Wv / (1.06 * (n - 1) + 2), 0.36 * Wv)
    gapv = 0.045 * Hv
    dots: list[tuple[float, float]] = []
    cells: list[Cell] = []
    for i in range(n):
        t = 0.5 if n <= 1 else i / (n - 1)
        nx = lab_w / 2 + t * (Wv - lab_w)
        ny = Hv / 2 + amp * math.sin(2 * math.pi * freq * t + phase)
        dots.append((nx, ny))
        up = (i % 2 == 0) == first_up
        top = ny - gapv - lab_h if up else ny + gapv
        lx = _clamp(nx - lab_w / 2, 0, Wv - lab_w)
        if vertical:
            cells.append(Cell(top, lx, lab_h, lab_w, order=i, dy=0, dx=-18 if up else 18,
                              s0=0.92, ease="outCubic", pad=14, extra={"up": up}))
        else:
            cells.append(Cell(lx, top, lab_w, lab_h, order=i, dy=-18 if up else 18,
                              s0=0.92, ease="outCubic", pad=14, extra={"up": up}))
    if vertical:
        dots = [(y, x) for x, y in dots]
    # The extra dict for vertical must have x/y swapped for dots too.
    return cells, {"dots": dots, "curve": _smooth_path(dots), "vertical": vertical}


def _fam_golden(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    sides = ["L", "T", "R", "B"]
    if r.random() < 0.5:
        sides.reverse()
    k = r.randrange(4)
    sides = sides[k:] + sides[:k]
    rho0 = 0.618 if n <= 3 else 0.56
    x, y, w, h = 0.0, 0.0, W, H
    gap = r.choice((8, 12, 16))
    cells: list[Cell] = []
    for i in range(n):
        if i == n - 1:
            cx, cy, cw, ch = x, y, w, h
        else:
            rho = rho0 if i == 0 else 0.52
            side = sides[i % 4]
            if side in ("L", "R"):
                cw, ch = w * rho, h
                cx, cy = (x, y) if side == "L" else (x + w - cw, y)
                if side == "L":
                    x, w = x + cw, w - cw
                else:
                    w = w - cw
            else:
                cw, ch = w, h * rho
                cx, cy = (x, y) if side == "T" else (x, y + h - ch)
                if side == "T":
                    y, h = y + ch, h - ch
                else:
                    h = h - ch
        ocx, ocy = cx + cw / 2, cy + ch / 2
        cells.append(Cell(
            cx + gap / 2, cy + gap / 2, cw - gap, ch - gap, order=i,
            dx=(W / 2 - ocx) / W * 60, dy=(H / 2 - ocy) / H * 60,
            s0=0.6, r0=r.choice((-90, 90)), ease="outExpo", lead=i == 0, pad=20,
        ))
    return cells, {"rho": rho0, "sides": "".join(sides)}


def _fam_bands(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    ws = [_clamp(it.weight, 1.0, 2.2) for it in items]
    gap = r.choice((6, 10, 14))
    avail = H - gap * (n - 1)
    y = 0.0
    flip = r.random() < 0.5
    mode = r.choice(("full", "stair", "alt", "taper", "wedge"))
    step = r.choice((0.04, 0.06, 0.08)) * W
    cells = []
    for i, wgt in enumerate(ws):
        ch = avail * wgt / sum(ws)
        alt = (i % 2 == 1) != flip
        x, cw = 0.0, W
        if mode == "stair":
            x, cw = step * i, W - step * (n - 1)
        elif mode == "alt":
            cw = W * 0.84
            x = 0.0 if alt else W - cw
        elif mode == "taper":
            shrink = step * min(i, n - 1 - i) * 1.6
            x, cw = shrink, W - 2 * shrink
        elif mode == "wedge":
            cw = W - step * i
            x = 0.0
        cells.append(Cell(x, y, cw, ch, order=i, dx=(30 if alt else -30), s0=0.98,
                          ease="outExpo", alt=alt, lead=i == 0, pad=22))
        y += ch + gap
    return cells, {"flip": flip, "gap": gap, "mode": mode}


def _fam_scatter(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    cols = max(2, math.ceil(math.sqrt(n * (W / H) * 0.55)))
    rows = max(1, math.ceil(n / cols))
    while cols * rows < n:
        cols += 1
    slots = list(range(cols * rows))
    r.shuffle(slots)
    slots = sorted(slots[:n])
    order_perm = list(range(n))
    r.shuffle(order_perm)
    cw, ch = W / cols, H / rows
    cells = []
    for i, s in enumerate(slots):
        c, rw = s % cols, s // cols
        bw, bh = cw * r.uniform(0.80, 0.90), ch * r.uniform(0.80, 0.90)
        jx = r.uniform(0, cw - bw)
        jy = r.uniform(0, ch - bh)
        cells.append(Cell(
            c * cw + jx, rw * ch + jy, bw, bh, rot=round(r.uniform(-3.4, 3.4), 2),
            order=order_perm[i], dy=-38, r0=r.choice((-14, 14)), s0=0.9, ease="outBack",
            pad=18, lead=i == 0,
        ))
    return cells, {"cols": cols, "rows": rows}


def _fam_slices(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    vertical = H > W
    Wv, Hv = (H, W) if vertical else (W, H)
    ws = [_clamp(it.weight, 0.9, 1.7) for it in items]
    mode = r.choice(("para", "chevron", "notch"))
    slant = r.choice((0.05, 0.07, 0.09)) * Wv
    sign = r.choice((1, -1))
    base = (Wv - slant) / sum(ws)
    x = 0.0
    cells = []
    for i, wgt in enumerate(ws):
        cw = base * wgt
        bw = cw + slant
        a = slant / bw * 100
        b = 100 - a
        if mode == "para":
            pts = [(a, 0), (100, 0), (b, 100), (0, 100)] if sign > 0 else [(0, 0), (b, 0), (100, 100), (a, 100)]
        elif mode == "chevron":
            pts = [(0, 0), (b, 0), (100, 50), (b, 100), (0, 100)] if sign > 0 else [(a, 0), (100, 0), (100, 100), (a, 100), (0, 50)]
        else:
            pts = [(0, 0), (b, 0), (100, 50), (b, 100), (0, 100), (a, 50)] if sign > 0 else [(a, 0), (100, 0), (b, 50), (100, 100), (a, 100), (0, 50)]
        if vertical:
            pts = [(py, px) for px, py in pts]
        poly = "polygon(" + ",".join(f"{px:.2f}% {py:.2f}%" for px, py in pts) + ")"
        if vertical:
            cells.append(Cell(0, x, W, bw, clip=poly, order=i, dx=-30, s0=0.9, sy0=0.05,
                              ease="outExpo", origin="50% 0%", pad=slant * 0.6 + 16,
                              lead=i == 0, extra={"slant": slant}))
        else:
            cells.append(Cell(x, 0, bw, H, clip=poly, order=i, dy=8, s0=0.9, sx0=0.05,
                              ease="outExpo", origin="0% 50%", pad=slant * 0.6 + 16,
                              lead=i == 0, extra={"slant": slant}))
        x += cw
    return cells, {"mode": mode, "sign": sign, "slant": round(slant)}


def _fam_skyline(items: list[Item], W: float, H: float, r: random.Random) -> tuple[list[Cell], dict]:
    n = len(items)
    vertical = H > W
    Wv, Hv = (H, W) if vertical else (W, H)
    ws = [it.weight for it in items]
    lo, hi = min(ws), max(ws)
    if hi - lo < 0.15:
        ws = [1.0 + 0.9 * (0.5 + 0.5 * math.sin(i * 1.7 + r.uniform(0, 6))) for i in range(n)]
        lo, hi = min(ws), max(ws)
    align = r.choice(("base", "top", "mid"))
    marimekko = r.random() < 0.5
    gap = r.choice((6, 10, 14, 18))
    floor_ = r.choice((0.36, 0.44, 0.52))
    if marimekko:
        span = [_clamp(w, 1.0, 2.4) for w in ws]
    else:
        span = [1.0] * n
    unit = (Wv - gap * (n - 1)) / sum(span)
    cells = []
    pos = 0.0
    for i, w in enumerate(ws):
        frac = floor_ + (1 - floor_) * ((w - lo) / (hi - lo if hi > lo else 1))
        ch = Hv * frac
        cw = unit * span[i]
        if align == "base":
            y0 = Hv - ch
        elif align == "top":
            y0 = 0.0
        else:
            y0 = (Hv - ch) / 2
        origin_y = {"base": "100%", "top": "0%", "mid": "50%"}[align]
        if vertical:
            # Portrait bars run along x. "top" is the far edge, "base" the near edge.
            if align == "top":
                bx, origin = max(0.0, W - ch), "100% 50%"
            elif align == "mid":
                bx, origin = max(0.0, (W - ch) / 2), "50% 50%"
            else:
                bx, origin = 0.0, "0% 50%"
            cells.append(Cell(bx, pos, min(ch, W), cw, order=i, s0=0.9, sx0=0.03,
                              ease="outExpo", origin=origin, pad=16, lead=i == 0,
                              extra={"align": align}))
        else:
            cells.append(Cell(pos, y0, cw, ch, order=i, s0=0.9, sy0=0.03, ease="outExpo",
                              origin=f"50% {origin_y}", pad=16, lead=i == 0,
                              extra={"align": align}))
        pos += cw + gap
    return cells, {"gap": gap, "align": align, "marimekko": marimekko}


_FAM_FN = {
    "treemap": _fam_treemap, "orbit": _fam_orbit, "cascade": _fam_cascade,
    "masonry": _fam_masonry, "path": _fam_path, "golden": _fam_golden,
    "bands": _fam_bands, "scatter": _fam_scatter, "slices": _fam_slices,
    "skyline": _fam_skyline,
}


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------
def _overlap(a: Cell, b: Cell) -> float:
    ox = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    oy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    if ox <= 0 or oy <= 0:
        return 0.0
    return ox * oy


def check_cells(family: str, cells: list[Cell], W: float, H: float, tol: float = 0.02) -> bool:
    """True when every cell sits inside the box and cells do not collide."""
    for c in cells:
        if c.w < 60 or c.h < 44:
            return False
        if c.x < -1 or c.y < -1 or c.x + c.w > W + 1 or c.y + c.h > H + 1:
            return False
    if family in ("slices",):
        return True
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            ov = _overlap(cells[i], cells[j])
            if ov and ov > tol * min(cells[i].w * cells[i].h, cells[j].w * cells[j].h):
                return False
    return True


def fits(family: str, n: int, vertical: bool, kind: str = "bullets") -> bool:
    lo, hi = _FIT[family]
    if not (lo <= n <= hi):
        return False
    if family not in _KIND_FAMILIES.get(kind, FAMILIES):
        return False
    if family == "masonry" and vertical and n < 4:
        return False
    if family == "golden" and vertical and n > 4:
        return False
    if family == "orbit" and vertical and n > 6:
        return False
    return True


def _signature(family: str, cells: list[Cell], W: float, H: float) -> str:
    parts = [family]
    for c in cells:
        parts.append(
            f"{round(c.x / W * 40)}.{round(c.y / H * 40)}.{round(c.w / W * 40)}.{round(c.h / H * 40)}"
            f".{int(c.rot)}.{c.clip}"
        )
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _pct(v: float, total: float) -> str:
    return f"{v / total * 100:.3f}%"


def _render(
    family: str, items: list[Item], cells: list[Cell], meta: dict,
    W: float, H: float, seed: str, *, recap: bool, kind: str, tempo: float,
) -> str:
    r = _rng(seed + ":render")
    parts: list[str] = []
    svg = ""
    vb = f'viewBox="0 0 {W:.0f} {H:.0f}" preserveAspectRatio="none"'
    if family == "orbit":
        paths = "".join(
            f'<path d="M{a:.1f},{b:.1f} L{c:.1f},{d:.1f}" '
            f'data-anim-from="{0.20 + 0.06 * (i + 1) * tempo:.2f}" data-anim-dur="0.42"/>'
            for i, (a, b, c, d) in enumerate(meta["spokes"])
        )
        svg = f'<svg class="lx-line" {vb} aria-hidden="true">{paths}</svg>'
    elif family == "path":
        d = _smooth_path(meta["dots"])
        svg = (
            f'<svg class="lx-line" {vb} aria-hidden="true">'
            f'<path d="{d}" data-anim-from="0.10" data-anim-dur="{0.55 + 0.1 * len(items):.2f}"/></svg>'
        )
        for i, (x, y) in enumerate(meta["dots"]):
            parts.append(
                f'<span class="lx-dot" style="left:{x / W * 100:.3f}%;top:{y / H * 100:.3f}%" '
                f'data-s0="0" data-ease="outBack" data-anim-from="{0.16 + 0.11 * i * tempo:.2f}" data-anim-dur="0.34"></span>'
            )
    parts.insert(0, svg)

    stag = 0.075 * tempo
    for i, (it, c) in enumerate(zip(items, cells)):
        pad_x = max(c.pad, (1 - c.inner) / 2 * c.w)
        pad_y = max(c.pad, (1 - c.inner) / 2 * c.h)
        bw = max(20.0, c.w - 2 * pad_x)
        bh = max(20.0, c.h - 2 * pad_y)
        has_n = family not in ("orbit", "path") or kind == "steps"
        nfs = 0.0
        # Row layouts put the numeral beside the sentence, so the text box is narrower.
        if family == "bands" and has_n:
            nfs = _clamp(c.h * 0.5, 20, min(64.0, max(20.0, c.h - 8)))
            bw = max(20.0, bw - nfs * 1.7 - 28)
        elif family == "cascade" and has_n:
            bw = max(20.0, bw - 64)
        elif family == "golden" and has_n:
            nfs = _clamp(min(c.w, c.h) * 0.38, 22, min(110.0, c.h * 0.5))
        head_h = nfs * 0.45 if family == "golden" and nfs else 0.0
        if has_n and family in ("treemap", "masonry", "cascade", "scatter", "skyline", "slices"):
            head_h += 26.0
        if it.value:
            head_h += min(56.0, bh * 0.34)
        if it.detail:
            head_h += min(40.0, bh * 0.22)
        hi_fs = 30 + 22 * _clamp((c.w * c.h) / (W * H) * 3.2, 0, 1)
        if c.lead and family in ("treemap", "golden", "orbit"):
            hi_fs += 6
        fs = fit_font(it.text, bw, bh, lo=15, hi=int(hi_fs), extra_h=head_h)
        t = round(_clamp((it.weight - 1) / 2.2, 0, 1), 2)
        delay = 0.14 + stag * c.order
        st = [
            f"left:{_pct(c.x, W)}", f"top:{_pct(c.y, H)}",
            f"width:{_pct(c.w, W)}", f"height:{_pct(c.h, H)}",
            f"--fs:{fs}px", f"--t:{t}", f"--pad-x:{pad_x:.0f}px", f"--pad-y:{pad_y:.0f}px",
            f"--i:{i + 1}",
        ]
        if nfs:
            st.append(f"--nfs:{nfs:.0f}px")
        if c.rot:
            st.append(f"--rot:{c.rot}deg")
        if c.clip:
            st.append(f"clip-path:{c.clip}")
        data = [
            f'data-dx="{c.dx:.1f}"', f'data-dy="{c.dy:.1f}"', f'data-s0="{c.s0}"',
            f'data-r0="{c.r0}"', f'data-ease="{c.ease}"', f'data-origin="{c.origin}"',
            f'data-anim-from="{delay:.2f}"', 'data-anim-dur="0.5"',
        ]
        if c.sx0 is not None:
            data.append(f'data-sx="{c.sx0}"')
        if c.sy0 is not None:
            data.append(f'data-sy="{c.sy0}"')
        cls = "lx-c"
        if c.lead:
            cls += " is-lead"
        if c.alt:
            cls += " is-alt"
        if c.extra.get("up") is True:
            cls += " is-up"
        elif c.extra.get("up") is False:
            cls += " is-down"
        idx_txt = "✓" if recap else f"{it.n:02d}"
        n_html = f'<span class="lx-n">{idx_txt}</span>' if has_n else ""
        v_html = f'<b class="lx-v">{html.escape(it.value)}</b>' if it.value else ""
        d_html = f'<span class="lx-d">{html.escape(it.detail)}</span>' if it.detail else ""
        parts.append(
            f'<div class="{cls}" style="{";".join(st)}" {" ".join(data)}>'
            f'{n_html}{v_html}<span class="lx-t">{html.escape(it.text)}</span>{d_html}</div>'
        )
    return "".join(parts)


def synthesize(
    items: list[Item],
    *,
    seed: str,
    vertical: bool,
    box: tuple[float, float],
    family_order: tuple[str, ...] = FAMILIES,
    used: Counter | None = None,
    sigs: set[str] | None = None,
    last_family: str = "",
    kind: str = "bullets",
    recap: bool = False,
    tempo: float = 1.0,
    forced: str = "",
) -> dict | None:
    """Compute a unique layout for ``items``.

    Returns ``{"html", "family", "sig", "height"}`` or ``None`` when the items
    cannot be laid out (caller falls back to a stock renderer).
    """
    n = len(items)
    W, H = box
    used = used if used is not None else Counter()
    sigs = sigs if sigs is not None else set()
    cands = [f for f in family_order if fits(f, n, vertical, kind)]
    if forced and forced in cands:
        cands = [forced]
    if not cands:
        return None
    if recap and not forced:
        pref = [c for c in cands if c in ("bands", "cascade", "path", "slices", "treemap", "golden")]
        if pref:
            pick = pref[_h(seed + ":recap") % len(pref)]
            cands = [pick] + [c for c in cands if c != pick]
    # least-used first, keep template preference order as tie-break, avoid repeat
    ranked = sorted(cands, key=lambda f: (f == last_family, used[f], cands.index(f)))
    for fam in ranked:
        for attempt in range(14):
            r = _rng(f"{seed}:{fam}:{attempt}")
            cells, meta = _FAM_FN[fam](items, W, H, r)
            if len(cells) != n or not check_cells(fam, cells, W, H):
                continue
            sig = _signature(fam, cells, W, H)
            if sig in sigs:
                continue
            sigs.add(sig)
            used[fam] += 1
            body = _render(fam, items, cells, meta, W, H, f"{seed}:{fam}:{attempt}",
                           recap=recap, kind=kind, tempo=tempo)
            html_out = (
                f'<div class="lx reveal" data-fam="{fam}" data-sig="{sig}">{body}</div>'
            )
            return {"html": html_out, "family": fam, "sig": sig, "height": H}
    return None


def motif_html(seed: str, motif: str) -> str:
    """Per-slide background motif layer (position / scale / rotation vary)."""
    if not motif or motif == "none":
        return ""
    r = _rng(seed + ":motif")
    return (
        '<div class="motif" aria-hidden="true" '
        f'style="--mx:{r.randrange(0, 100)}%;--my:{r.randrange(0, 100)}%;'
        f'--ms:{r.uniform(0.8, 1.7):.2f};--mr:{r.randrange(0, 180)}deg"></div>'
    )


# ---------------------------------------------------------------------------
# per-template fingerprint
# ---------------------------------------------------------------------------
_PROFILE_SPACE = len(FAMILIES) * len(MOTIFS) * len(HTYPES)  # 420
_profile_cache: dict[tuple[str, ...], dict[str, dict]] = {}


def template_profiles(keys: list[str] | tuple[str, ...]) -> dict[str, dict]:
    """Assign every template a collision-free (family lead, motif, heading, tempo)."""
    ck = tuple(sorted(keys))
    if ck in _profile_cache:
        return _profile_cache[ck]
    taken: set[int] = set()
    out: dict[str, dict] = {}
    for key in ck:
        slot = _h("profile:" + key) % _PROFILE_SPACE
        while slot in taken:
            slot = (slot + 1) % _PROFILE_SPACE
        taken.add(slot)
        fam_i = slot % len(FAMILIES)
        motif_i = (slot // len(FAMILIES)) % len(MOTIFS)
        head_i = (slot // (len(FAMILIES) * len(MOTIFS))) % len(HTYPES)
        rr = _rng("order:" + key)
        rest = [f for f in FAMILIES if f != FAMILIES[fam_i]]
        rr.shuffle(rest)
        out[key] = {
            "families": (FAMILIES[fam_i], *rest),
            "motif": MOTIFS[motif_i],
            "htype": HTYPES[head_i],
            "tempo": (0.75, 1.0, 1.25, 1.5)[_h("tempo:" + key) % 4],
            "slot": slot,
        }
    _profile_cache[ck] = out
    return out


def template_fingerprint(profile: dict) -> tuple:
    return (profile["families"][0], profile["motif"], profile["htype"])


# ---------------------------------------------------------------------------
# CSS + JS injected into the slideshow
# ---------------------------------------------------------------------------
LX_CSS = r"""
  /* ---- Layout synthesizer (computed geometry, per-family look) --------- */
  .lx { position:relative; width:100%; height:min(590px, calc(100vh - 460px)); min-height:0; }
  body.vertical .lx { height:min(1100px, calc(100vh - 640px)); }
  .lx-c {
    position:absolute; display:flex; flex-direction:column; justify-content:center; gap:.3em;
    padding:var(--pad-y,16px) var(--pad-x,16px); overflow:hidden; min-width:0; min-height:0;
    border-radius:var(--card-radius,16px); color:var(--ink); font-family:var(--font);
    background:color-mix(in srgb, var(--a) calc(8% + var(--t,0) * 20%), var(--panel));
    border:1.5px solid color-mix(in srgb, var(--a) 34%, transparent);
    rotate:var(--rot,0deg); transition:none;
  }
  .lx-t { font-size:var(--fs,26px); font-weight:650; line-height:1.2; overflow-wrap:anywhere; min-width:0; }
  .lx-n { font-size:13px; font-weight:800; letter-spacing:.1em; color:var(--a); font-variant-numeric:tabular-nums; }
  .lx-v { font-size:clamp(18px, calc(var(--fs,26px) * 1.35), 56px); font-weight:800; line-height:1; color:var(--a); letter-spacing:-.02em; }
  .lx-d { font-size:max(14px, calc(var(--fs,26px) * .58)); color:var(--muted); line-height:1.3; }
  .lx-line { position:absolute; inset:0; width:100%; height:100%; overflow:visible; pointer-events:none; }
  .lx-line path { fill:none; stroke:color-mix(in srgb, var(--a) 62%, transparent); stroke-width:2.5; stroke-linecap:round; vector-effect:non-scaling-stroke; }
  .lx-dot { position:absolute; width:22px; height:22px; margin:-11px 0 0 -11px; border-radius:50%; background:var(--a); box-shadow:0 0 0 6px color-mix(in srgb, var(--a) 24%, transparent), 0 0 24px color-mix(in srgb, var(--glow) 70%, transparent); }
  .lx-c.is-active { z-index:5; scale:1.03; border-color:color-mix(in srgb, var(--a) 78%, transparent); box-shadow:0 0 0 2px color-mix(in srgb, var(--a) 55%, transparent), 0 18px 46px color-mix(in srgb, var(--glow) 34%, transparent); }
  .lx-c.is-lead .lx-t { font-weight:750; }

  /* treemap: tiled slabs, lead cell dominant */
  .lx[data-fam="treemap"] .lx-c { border-radius:10px; justify-content:flex-end; }
  .lx[data-fam="treemap"] .lx-c.is-lead { background:linear-gradient(145deg, color-mix(in srgb, var(--a) 34%, var(--panel)), color-mix(in srgb, var(--b) 18%, var(--panel))); }
  /* orbit: discs around a hub */
  .lx[data-fam="orbit"] .lx-c { border-radius:50%; align-items:center; text-align:center; justify-content:center; }
  .lx[data-fam="orbit"] .lx-c.is-lead { background:radial-gradient(circle at 35% 30%, color-mix(in srgb, var(--a) 42%, var(--panel)), color-mix(in srgb, var(--b) 16%, var(--panel))); border-width:2.5px; }
  .lx[data-fam="orbit"] .lx-n { display:none; }
  /* cascade: offset stair cards with a spine */
  .lx[data-fam="cascade"] .lx-c { flex-direction:row; align-items:center; gap:18px; border-left:8px solid var(--a); border-radius:6px 22px 22px 6px; }
  .lx[data-fam="cascade"] .lx-n { flex:none; font-size:28px; opacity:.9; }
  /* masonry: uneven columns, top-accent */
  .lx[data-fam="masonry"] .lx-c { border-top:6px solid var(--a); border-radius:6px 6px 18px 18px; justify-content:flex-start; }
  /* path: floating labels on a drawn line */
  .lx[data-fam="path"] .lx-c { background:transparent; border:0; border-bottom:3px solid color-mix(in srgb, var(--a) 60%, transparent); border-radius:0; text-align:center; align-items:center; }
  .lx[data-fam="path"] .lx-c.is-up { justify-content:flex-end; }
  .lx[data-fam="path"] .lx-c.is-down { justify-content:flex-start; border-bottom:0; border-top:3px solid color-mix(in srgb, var(--a) 60%, transparent); }
  .lx[data-fam="path"] .lx-n { display:none; }
  /* golden: frameless panels, huge ghost numeral */
  .lx[data-fam="golden"] .lx-c { border:0; border-radius:4px; justify-content:flex-start; }
  .lx[data-fam="golden"] .lx-n { position:absolute; right:10px; bottom:4px; font-size:var(--nfs,64px); line-height:.85; letter-spacing:-.04em; max-width:68%; overflow:hidden; pointer-events:none; color:transparent; -webkit-text-stroke:2px color-mix(in srgb, var(--a) 48%, transparent); }
  /* bands: editorial rows, outlined numerals */
  .lx[data-fam="bands"] .lx-c { background:transparent; border:0; border-top:2px solid color-mix(in srgb, var(--a) 46%, transparent); border-radius:0; flex-direction:row; align-items:center; gap:28px; }
  .lx[data-fam="bands"] .lx-c.is-alt { flex-direction:row-reverse; text-align:right; }
  .lx[data-fam="bands"] .lx-n { flex:none; font-size:var(--nfs,40px); line-height:1; color:transparent; -webkit-text-stroke:2px var(--a); letter-spacing:-.03em; min-width:1.6em; text-align:center; }
  .lx[data-fam="bands"] .lx-t, .lx[data-fam="cascade"] .lx-t { flex:1 1 auto; min-width:0; }
  .lx[data-fam="bands"] .lx-c.is-active { background:color-mix(in srgb, var(--a) 12%, transparent); box-shadow:none; }
  /* scatter: pinned notes */
  .lx[data-fam="scatter"] .lx-c { border-radius:6px; box-shadow:0 14px 30px rgba(0,0,0,.22); border-width:1px; justify-content:flex-start; }
  .lx[data-fam="scatter"] .lx-c::before { content:""; position:absolute; top:-2px; left:50%; width:54px; height:16px; margin-left:-27px; background:color-mix(in srgb, var(--a) 52%, transparent); opacity:.85; border-radius:2px; }
  /* slices: slanted panels */
  .lx[data-fam="slices"] .lx-c { border:0; border-radius:0; background:linear-gradient(160deg, color-mix(in srgb, var(--a) calc(14% + var(--t,0) * 24%), var(--panel)), color-mix(in srgb, var(--b) 8%, var(--panel))); justify-content:center; text-align:center; align-items:center; }
  .lx[data-fam="slices"] .lx-c.is-active { box-shadow:none; filter:drop-shadow(0 0 14px color-mix(in srgb, var(--glow) 60%, transparent)); }
  /* skyline: pillars rising from a baseline */
  .lx[data-fam="skyline"] .lx-c { justify-content:flex-start; border-radius:14px 14px 4px 4px; border-bottom:0; background:linear-gradient(180deg, color-mix(in srgb, var(--a) calc(22% + var(--t,0) * 24%), var(--panel)), color-mix(in srgb, var(--a) 4%, transparent)); }
  body.vertical .lx[data-fam="skyline"] .lx-c { border-radius:4px 14px 14px 4px; background:linear-gradient(90deg, color-mix(in srgb, var(--a) calc(22% + var(--t,0) * 24%), var(--panel)), color-mix(in srgb, var(--a) 4%, transparent)); justify-content:center; }

  /* background motifs — one per template, offset/scale/rotation per slide */
  .motif { position:absolute; inset:0; pointer-events:none; opacity:.6; }
  body[data-motif="dots"] .motif { background-image:radial-gradient(circle, color-mix(in srgb, var(--a) 34%, transparent) 1.8px, transparent 2.4px); background-size:calc(30px * var(--ms)) calc(30px * var(--ms)); background-position:var(--mx) var(--my); -webkit-mask-image:radial-gradient(ellipse at var(--mx) var(--my), #000 0, transparent 75%); mask-image:radial-gradient(ellipse at var(--mx) var(--my), #000 0, transparent 75%); }
  body[data-motif="rings"] .motif { background:repeating-radial-gradient(circle at var(--mx) var(--my), transparent 0 calc(44px * var(--ms)), color-mix(in srgb, var(--a) 18%, transparent) calc(44px * var(--ms)) calc(46px * var(--ms))); -webkit-mask-image:radial-gradient(circle at var(--mx) var(--my), #000 0, transparent 70%); mask-image:radial-gradient(circle at var(--mx) var(--my), #000 0, transparent 70%); }
  body[data-motif="diag"] .motif { background:repeating-linear-gradient(var(--mr), transparent 0 calc(30px * var(--ms)), color-mix(in srgb, var(--a) 13%, transparent) calc(30px * var(--ms)) calc(32px * var(--ms))); }
  body[data-motif="grid"] .motif { background-image:linear-gradient(color-mix(in srgb, var(--a) 12%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--a) 12%, transparent) 1px, transparent 1px); background-size:calc(56px * var(--ms)) calc(56px * var(--ms)); background-position:var(--mx) var(--my); }
  body[data-motif="waves"] .motif { background:repeating-radial-gradient(ellipse 220px 90px at var(--mx) 110%, transparent 0 calc(26px * var(--ms)), color-mix(in srgb, var(--a) 15%, transparent) calc(26px * var(--ms)) calc(28px * var(--ms))); }
  body[data-motif="cross"] .motif { background-image:linear-gradient(color-mix(in srgb, var(--a) 22%, transparent) 2px, transparent 2px), linear-gradient(90deg, color-mix(in srgb, var(--a) 22%, transparent) 2px, transparent 2px); background-size:calc(120px * var(--ms)) calc(120px * var(--ms)); background-position:calc(var(--mx) - 6px) calc(var(--my) - 6px); -webkit-mask-image:radial-gradient(circle, #000 1.5px, transparent 2px); mask-image:radial-gradient(circle, #000 1.5px, transparent 2px); -webkit-mask-size:calc(120px * var(--ms)) calc(120px * var(--ms)); mask-size:calc(120px * var(--ms)) calc(120px * var(--ms)); }

  /* heading treatments — one per template */
  body[data-htype="bar"] .slide h2 { border-left:8px solid var(--a); padding-left:.4em; }
  body[data-htype="sweep"] .slide h2 { position:relative; padding-bottom:.22em; }
  body[data-htype="sweep"] .slide h2::after { content:""; position:absolute; left:0; bottom:0; width:38%; height:5px; border-radius:5px; background:linear-gradient(90deg, var(--a), transparent); }
  body[data-htype="caps"] .slide h2 { text-transform:uppercase; letter-spacing:.06em; font-size:.82em; }
  body[data-htype="marker"] .slide h2 { background:linear-gradient(transparent 62%, color-mix(in srgb, var(--a) 30%, transparent) 62%); width:fit-content; padding:0 .2em; }
  body[data-htype="offset"] .slide h2 { text-shadow:3px 3px 0 color-mix(in srgb, var(--a) 40%, transparent); }
"""

LX_JS = r"""
  // ---- Layout synthesizer poses (seek-safe: transform / opacity / dashoffset) ----
  function lxPose(t, frame, f0, f1) {
    const el = t.el, d = el.dataset || {};
    if (el.tagName && el.tagName.toLowerCase() === 'path') {
      const e = interpolate(frame, [f0, f1], [0, 1], easings.outCubic);
      let len = 1000;
      try { len = el.getTotalLength(); } catch (err) {}
      el.style.strokeDasharray = String(len);
      el.style.strokeDashoffset = String(len * (1 - e));
      return { transform: '', filter: '' };
    }
    const ease = easings[d.ease] || easings.outCubic;
    const e = interpolate(frame, [f0, f1], [0, 1], ease);
    el.__lxEnd = f1;
    const host = el.parentElement;
    const W = (host && host.clientWidth) || 1, H = (host && host.clientHeight) || 1;
    const dx = (parseFloat(d.dx) || 0) / 100 * W * (1 - e);
    const dy = (parseFloat(d.dy) || 0) / 100 * H * (1 - e);
    const r0 = (parseFloat(d.r0) || 0) * (1 - e);
    const s0 = d.s0 !== undefined && d.s0 !== '' ? parseFloat(d.s0) : 0.85;
    const sx0 = d.sx !== undefined ? parseFloat(d.sx) : s0;
    const sy0 = d.sy !== undefined ? parseFloat(d.sy) : s0;
    const sx = sx0 + (1 - sx0) * e, sy = sy0 + (1 - sy0) * e;
    if (d.origin) el.style.transformOrigin = d.origin;
    const b = 7 * (1 - Math.min(1, Math.max(0, e)));
    return {
      transform: `translate(${dx}px, ${dy}px) rotate(${r0}deg) scale(${sx}, ${sy})`,
      filter: `blur(${b}px)`,
    };
  }
  // Guardrail (Beautiful.ai-style): shrink any cell whose text still overflows.
  function lxFit(slide) {
    // Fill the gap under the heading without covering the caption. A fixed
    // percentage height collapses here because the scene sizes to its content.
    slide.querySelectorAll('.lx').forEach((lx) => {
      const cap = slide.querySelector('.caption');
      const top = lx.getBoundingClientRect().top;
      const limit = (cap ? cap.getBoundingClientRect().top : window.innerHeight) - 16;
      const avail = Math.floor(limit - top);
      if (avail > 120) lx.style.height = avail + 'px';
    });
    slide.querySelectorAll('.lx-c').forEach((c) => {
      const cs = getComputedStyle(c);
      let fs = parseFloat(cs.getPropertyValue('--fs')) || 26;
      const padB = parseFloat(cs.paddingBottom) || 0, padR = parseFloat(cs.paddingRight) || 0;
      const kids = [...c.querySelectorAll('.lx-t, .lx-d, .lx-v, .lx-n')]
        .filter((k) => getComputedStyle(k).position !== 'absolute');
      const over = () => kids.some((k) =>
        k.offsetTop < -1 || k.offsetTop + k.offsetHeight > c.clientHeight - padB + 1 ||
        k.offsetLeft + k.offsetWidth > c.clientWidth - padR + 1);
      let guard = 0;
      while (guard++ < 16 && fs > 13 && over()) {
        fs = Math.max(13, fs * 0.93);
        c.style.setProperty('--fs', fs.toFixed(1) + 'px');
      }
    });
  }
"""
