"""Built-in per-key color themes for the custom effect.

A theme is a horizontal gradient computed from each key's position on the board,
plus optional accent keys with fixed colors.
"""

from dataclasses import dataclass, field

from . import keymap as K

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    stops: list[tuple[float, RGB]]  # (position 0..1 from left to right, color)
    accents: dict[str, RGB] = field(default_factory=dict)


def _gradient(stops: list[tuple[float, RGB]], t: float) -> RGB:
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return stops[-1][1]


def render(preset: Preset) -> dict[int, RGB]:
    """Compute {matrix index: color} for every key on the board."""
    placed = [(idx, (r[0] + r[2]) / 2) for idx, _, _, r in K.KEYS if r != (0, 0, 0, 0)]
    lo = min(x for _, x in placed)
    hi = max(x for _, x in placed)
    colors = {idx: _gradient(preset.stops, (x - lo) / (hi - lo)) for idx, x in placed}
    for key, rgb in preset.accents.items():
        colors[K.key_index(key)] = rgb
    return colors


_WHITE_NAV = {k: (0xFF, 0xFF, 0xFF) for k in ("w", "a", "s", "d", "up", "down", "left", "right")}

PRESETS = [
    Preset("synthwave", "purple → pink → cyan, white WASD/arrows, orange Esc",
           [(0.0, (0x60, 0x00, 0xFF)), (0.5, (0xFF, 0x00, 0x90)), (1.0, (0x00, 0xD5, 0xFF))],
           {**_WHITE_NAV, "esc": (0xFF, 0x50, 0x00)}),
]
PRESET_BY_NAME = {p.name: p for p in PRESETS}
