"""Built-in per-key color themes for the custom effect.

A theme is a gradient computed from each key's position on the board, plus
optional accent keys with fixed colors. The gradient runs left to right ("x"),
top to bottom ("y"), along the diagonal from the top left ("diagonal") or from
the middle of the board outwards ("center").
"""

import functools
import math
from dataclasses import dataclass, field

from . import keymap as K

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    stops: list[tuple[float, RGB]]  # (position 0..1 along the direction, color)
    accents: dict[str, RGB] = field(default_factory=dict)
    direction: str = "x"  # x, y, diagonal or center


def _gradient(stops: list[tuple[float, RGB]], t: float) -> RGB:
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return stops[-1][1]


# key centers and the extent of the board
_CENTERS = [(idx, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2) for idx, _, _, r in K.KEYS if r != (0, 0, 0, 0)]
_X0, _X1 = min(x for _, x, _ in _CENTERS), max(x for _, x, _ in _CENTERS)
_Y0, _Y1 = min(y for _, _, y in _CENTERS), max(y for _, _, y in _CENTERS)


def _position(direction: str, x: float, y: float) -> float:
    if direction == "x":
        return x
    if direction == "y":
        return y
    if direction == "diagonal":
        return x + y
    if direction == "center":
        # elliptical, so the rings follow the shape of the board
        return math.hypot((x - (_X0 + _X1) / 2) / (_X1 - _X0), (y - (_Y0 + _Y1) / 2) / (_Y1 - _Y0))
    raise ValueError(f"unknown gradient direction: {direction!r}")


@functools.cache
def positions(direction: str) -> dict[int, float]:
    """{matrix index: 0..1} along a gradient direction, for every key with an LED."""
    placed = [(idx, _position(direction, x, y)) for idx, x, y in _CENTERS]
    lo = min(v for _, v in placed)
    hi = max(v for _, v in placed)
    return {idx: (v - lo) / (hi - lo) for idx, v in placed}


def color_at(preset: Preset, t: float) -> RGB:
    """The theme's gradient color at position t (0..1)."""
    return _gradient(preset.stops, t)


def render(preset: Preset) -> dict[int, RGB]:
    """Compute {matrix index: color} for every key on the board."""
    colors = {idx: _gradient(preset.stops, t) for idx, t in positions(preset.direction).items()}
    for key, rgb in preset.accents.items():
        colors[K.key_index(key)] = rgb
    return colors


_NAV = ("w", "a", "s", "d", "up", "down", "left", "right")
_WHITE_NAV = {k: (0xFF, 0xFF, 0xFF) for k in _NAV}


def _keys(rgb: RGB, *names: str) -> dict[str, RGB]:
    return {k: rgb for k in names}

PRESETS = [
    Preset("synthwave", "purple → pink → cyan, white WASD/arrows, orange Esc",
           [(0.0, (0x60, 0x00, 0xFF)), (0.5, (0xFF, 0x00, 0x90)), (1.0, (0x00, 0xD5, 0xFF))],
           {**_WHITE_NAV, "esc": (0xFF, 0x50, 0x00)}),
    Preset("cyberpunk", "neon yellow → hot pink → cyan, white WASD/arrows, red Esc",
           [(0.0, (0xFA, 0xEA, 0x2B)), (0.5, (0xFF, 0x00, 0x3C)), (1.0, (0x00, 0xE5, 0xFF))],
           {**_WHITE_NAV, "esc": (0xFF, 0x00, 0x00), "enter": (0xFF, 0x00, 0x3C)}),
    Preset("dracula", "deep purple → pink → cyan, yellow WASD, green Esc",
           [(0.0, (0x62, 0x72, 0xA4)), (0.5, (0xFF, 0x79, 0xC6)), (1.0, (0x8B, 0xE9, 0xFD))],
           {"w": (0xF1, 0xFA, 0x8C), "a": (0xF1, 0xFA, 0x8C), "s": (0xF1, 0xFA, 0x8C), "d": (0xF1, 0xFA, 0x8C), "esc": (0x50, 0xFA, 0x7B), "enter": (0xFF, 0xB8, 0x6C)}),
    Preset("matrix", "dark green → bright green → dark green, red Esc",
           [(0.0, (0x00, 0x33, 0x00)), (0.5, (0x00, 0xFF, 0x00)), (1.0, (0x00, 0x33, 0x00))],
           {**_WHITE_NAV, "esc": (0xFF, 0x00, 0x00)}),
    Preset("sunset", "deep purple → orange → yellow, white WASD",
           [(0.0, (0x2B, 0x0F, 0x54)), (0.5, (0xFF, 0x7B, 0x00)), (1.0, (0xFF, 0xC8, 0x00))],
           {**_WHITE_NAV, "esc": (0xFF, 0xFF, 0xFF)}),
    Preset("volcano", "dark red → bright orange → yellow, cyan WASD/Esc",
           [(0.0, (0x33, 0x00, 0x00)), (0.4, (0xFF, 0x00, 0x00)), (0.7, (0xFF, 0x66, 0x00)), (1.0, (0xFF, 0xCC, 0x00))],
           {"w": (0x00, 0xFF, 0xFF), "a": (0x00, 0xFF, 0xFF), "s": (0x00, 0xFF, 0xFF), "d": (0x00, 0xFF, 0xFF), "up": (0x00, 0xFF, 0xFF), "down": (0x00, 0xFF, 0xFF), "left": (0x00, 0xFF, 0xFF), "right": (0x00, 0xFF, 0xFF), "esc": (0x00, 0x88, 0xFF), "enter": (0x00, 0xFF, 0xFF)}),
    Preset("aurora", "deep blue → aurora green → purple, hot pink WASD",
           [(0.0, (0x0F, 0x0A, 0x3A)), (0.5, (0x00, 0xFF, 0x7F)), (1.0, (0x7B, 0x00, 0xFF))],
           {"w": (0xFF, 0x00, 0xAA), "a": (0xFF, 0x00, 0xAA), "s": (0xFF, 0x00, 0xAA), "d": (0xFF, 0x00, 0xAA), "esc": (0xFF, 0xFF, 0xFF), "enter": (0x00, 0xFF, 0xFF)}),
    Preset("miami-vice", "bright cyan → hot pink → purple, yellow WASD",
           [(0.0, (0x00, 0xFF, 0xCC)), (0.5, (0xFF, 0x00, 0x99)), (1.0, (0x66, 0x00, 0xFF))],
           {"w": (0xFF, 0xFF, 0x00), "a": (0xFF, 0xFF, 0x00), "s": (0xFF, 0xFF, 0x00), "d": (0xFF, 0xFF, 0x00), "esc": (0xFF, 0x00, 0x33), "space": (0xFF, 0xFF, 0x00)}),
    Preset("toxic", "dark grey → acid green → dark grey, purple WASD",
           [(0.0, (0x11, 0x11, 0x11)), (0.5, (0xCC, 0xFF, 0x00)), (1.0, (0x11, 0x11, 0x11))],
           {"w": (0xAA, 0x00, 0xFF), "a": (0xAA, 0x00, 0xFF), "s": (0xAA, 0x00, 0xFF), "d": (0xAA, 0x00, 0xFF), "up": (0xAA, 0x00, 0xFF), "down": (0xAA, 0x00, 0xFF), "left": (0xAA, 0x00, 0xFF), "right": (0xAA, 0x00, 0xFF), "esc": (0xCC, 0xFF, 0x00)}),
    Preset("rainbow", "the full spectrum from left to right",
           [(0.0, (0xFF, 0x00, 0x00)), (0.17, (0xFF, 0x80, 0x00)), (0.33, (0xFF, 0xF0, 0x00)),
            (0.5, (0x00, 0xFF, 0x00)), (0.67, (0x00, 0xC0, 0xFF)), (0.83, (0x30, 0x00, 0xFF)),
            (1.0, (0xC0, 0x00, 0xFF))]),
    Preset("ocean", "white surf on top → turquoise → deep blue at the bottom, coral WASD/arrows",
           [(0.0, (0xC8, 0xFF, 0xFF)), (0.35, (0x00, 0xE0, 0xD0)), (0.7, (0x00, 0x60, 0xFF)),
            (1.0, (0x00, 0x10, 0x90))],
           _keys((0xFF, 0x50, 0x40), *_NAV), "y"),
    Preset("fire", "yellow on top → orange → red at the bottom, like rising flames, white Esc",
           [(0.0, (0xFF, 0xE0, 0x20)), (0.45, (0xFF, 0x70, 0x00)), (1.0, (0xFF, 0x00, 0x00))],
           {"esc": (0xFF, 0xFF, 0xFF)}, "y"),
    Preset("forest", "golden canopy on top → leaf green → deep moss, amber WASD/arrows",
           [(0.0, (0xE0, 0xD0, 0x30)), (0.4, (0x40, 0xE0, 0x20)), (1.0, (0x00, 0x50, 0x10))],
           _keys((0xFF, 0x90, 0x00), *_NAV), "y"),
    Preset("sakura", "cherry pink → blossom white → pink on the diagonal, green Esc",
           [(0.0, (0xFF, 0x40, 0x90)), (0.5, (0xFF, 0xC8, 0xE0)), (1.0, (0xFF, 0x40, 0x90))],
           {"esc": (0x60, 0xFF, 0x60)}, "diagonal"),
    Preset("frost", "ice white in the top left → glacier blue → deep blue, white Esc/Enter",
           [(0.0, (0xE0, 0xF8, 0xFF)), (0.45, (0x60, 0xD0, 0xFF)), (1.0, (0x10, 0x30, 0xFF))],
           _keys((0xFF, 0xFF, 0xFF), "esc", "enter"), "diagonal"),
    Preset("vaporwave", "hot pink → violet → teal on the diagonal, yellow WASD",
           [(0.0, (0xFF, 0x30, 0xC0)), (0.5, (0x90, 0x40, 0xFF)), (1.0, (0x00, 0xFF, 0xD0))],
           _keys((0xFF, 0xE0, 0x00), "w", "a", "s", "d"), "diagonal"),
    Preset("galaxy", "pink core → violet → deep space blue at the edges, white stars",
           [(0.0, (0xFF, 0x60, 0xD0)), (0.35, (0x90, 0x20, 0xFF)), (0.7, (0x30, 0x10, 0xC0)),
            (1.0, (0x08, 0x08, 0x50))],
           _keys((0xFF, 0xFF, 0xFF), "f2", "f9", "q", "o", "h", "z", "period"), "center"),
    Preset("supernova", "white-hot center → yellow → orange → red edges",
           [(0.0, (0xFF, 0xFF, 0xE0)), (0.3, (0xFF, 0xD0, 0x00)), (0.65, (0xFF, 0x50, 0x00)),
            (1.0, (0xC0, 0x00, 0x10))], {}, "center"),
    Preset("nord", "frost blue → teal → aurora purple, snow white WASD/arrows, red Esc",
           [(0.0, (0x5E, 0x81, 0xAC)), (0.35, (0x88, 0xC0, 0xD0)), (0.65, (0x8F, 0xBC, 0xBB)),
            (1.0, (0xB4, 0x8E, 0xAD))],
           {**_keys((0xEC, 0xEF, 0xF4), *_NAV), "esc": (0xBF, 0x61, 0x6A)}),
    Preset("tokyo-night", "night blue → purple → neon red, cyan WASD/arrows, orange Esc",
           [(0.0, (0x7A, 0xA2, 0xF7)), (0.5, (0xBB, 0x9A, 0xF7)), (1.0, (0xF7, 0x76, 0x8E))],
           {**_keys((0x7D, 0xCF, 0xFF), *_NAV), "esc": (0xFF, 0x9E, 0x64)}),
    Preset("catppuccin", "mauve → pink → sky → green pastels, peach WASD/arrows",
           [(0.0, (0xCB, 0xA6, 0xF7)), (0.33, (0xF5, 0xC2, 0xE7)), (0.67, (0x89, 0xDC, 0xEB)),
            (1.0, (0xA6, 0xE3, 0xA1))],
           _keys((0xFA, 0xB3, 0x87), *_NAV)),
    Preset("gruvbox", "warm red → yellow → green → blue, orange Esc",
           [(0.0, (0xFB, 0x49, 0x34)), (0.33, (0xFA, 0xBD, 0x2F)), (0.67, (0xB8, 0xBB, 0x26)),
            (1.0, (0x83, 0xA5, 0x98))],
           {"esc": (0xFE, 0x80, 0x19)}),
    Preset("royal", "deep purple with gold WASD, arrows, Esc, Enter and Space",
           [(0.0, (0x30, 0x00, 0x80)), (0.5, (0x70, 0x00, 0xE0)), (1.0, (0x30, 0x00, 0x80))],
           _keys((0xFF, 0xB0, 0x00), *_NAV, "esc", "enter", "space")),
]
PRESET_BY_NAME = {p.name: p for p in PRESETS}
