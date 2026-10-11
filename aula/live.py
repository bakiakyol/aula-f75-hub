"""Animations played from the computer, frame by frame (real-time command 0x88).

Unlike the firmware effects these can show anything, e.g. a theme flowing across
the board. The keyboard only shows them while frames keep coming, so the GUI or
`aula animate` has to stay open; about 2 s after the last frame the keyboard goes
back to its own effect. Nothing is stored on the keyboard.

Every animation is a pure function of (theme, time), so the GUI can draw the
same frames it sends. Time runs faster or slower to change the speed.

What looks smooth on the keyboard was found by trying it on one (see encode()):
short frames, sent with gaps, in which every key stays in the same group from
one frame to the next.
"""

import colorsys
import math
import random
from dataclasses import dataclass
from typing import Callable

from . import keymap as K
from . import presets as T
from . import protocol as P

RGB = tuple[int, int, int]
FPS = 20         # at most this many frames per second (with P.LIVE_GAP about 14 get through)
BUDGET = 126     # bytes per frame (9 packets): longer frames get lost more often
SPARE = 2        # groups left for keys that stand out from their band (a key flashing)
STANDOUT = 40    # a key this far from its band's color doesn't take part in its average

_X = T.positions("x")
_Y = T.positions("y")
_rng = random.Random(75)
# fixed per-key randomness (sparkle timing, fire flicker), the same on every run
_SEED = {idx: (_rng.random(), _rng.random()) for idx in _X}
_WHITE = (255, 255, 255)
_rendered: dict[str, dict[int, RGB]] = {}


def _scale(c: RGB, v: float) -> RGB:
    v = max(0.0, min(1.0, v))
    return tuple(round(ch * v) for ch in c)


def _mix(a: RGB, b: RGB, f: float) -> RGB:
    f = max(0.0, min(1.0, f))
    return tuple(round(x + (y - x) * f) for x, y in zip(a, b))


def _distance(a: RGB, b: RGB) -> int:
    return max(abs(x - y) for x, y in zip(a, b))


def _theme(preset: T.Preset) -> dict[int, RGB]:
    if preset.name not in _rendered:
        _rendered[preset.name] = T.render(preset)
    return _rendered[preset.name]


def _accents(preset: T.Preset) -> dict[int, RGB]:
    return {K.key_index(k): rgb for k, rgb in preset.accents.items()}


def wave(preset: T.Preset, t: float) -> dict[int, RGB]:
    """The theme's gradient flows along its own direction, a bright crest riding on it."""
    out = {}
    for idx, p in T.positions(preset.direction).items():
        phase = p - t * 0.4
        u = phase % 2.0                                  # 0..2: there and back, so it loops
        c = T.color_at(preset, u if u <= 1 else 2 - u)
        crest = 0.5 + 0.5 * math.cos(2 * math.pi * phase)
        out[idx] = _mix(_scale(c, 0.35 + 0.65 * crest), _WHITE, 0.3 * crest ** 6)
    out.update(_accents(preset))
    return out


def breathe(preset: T.Preset, t: float) -> dict[int, RGB]:
    """The whole theme fades in and out."""
    seen = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * t * 0.3))   # brightness as the eye sees it
    v = seen ** 2.2                                      # LED power: the eye is far more sensitive when dim
    return {idx: _scale(c, v) for idx, c in _theme(preset).items()}


_TWINKLE = [(0.15, _WHITE), (0.45, (110, 110, 110))]   # (seconds, color): bright, then half


def sparkle(preset: T.Preset, t: float) -> dict[int, RGB]:
    """The theme glows dimly while keys twinkle white, here and there."""
    out = {}
    for idx, c in _theme(preset).items():
        phase, rate = _SEED[idx]
        period = 2.5 + 3.5 * rate
        age = (t + phase * period) % period
        out[idx] = next((tw for end, tw in _TWINKLE if age < end), _scale(c, 0.3))
    return out


def rainbow(_preset: T.Preset, t: float) -> dict[int, RGB]:
    """A rainbow moving from left to right."""
    out = {}
    for idx, x in _X.items():
        r, g, b = colorsys.hsv_to_rgb((x * 0.6 - t * 0.25) % 1.0, 1.0, 1.0)
        out[idx] = (round(r * 255), round(g * 255), round(b * 255))
    return out


@dataclass(frozen=True)
class _Fire:
    palette: T.Preset    # heat 0..1 -> color
    sparks: tuple[RGB, RGB, RGB]   # a spark's colors as it rises and cools
    trail: RGB           # the glow it leaves on the key below
    reach: float         # how high the flames climb (1: the whole board)
    pace: float          # how fast everything moves
    streams: int         # sparks in the air at a time (bursts add more)


_COLUMNS = 3             # flames rise and fall in this many columns


def _nearest_key(x: float, y: float) -> int:
    return min(_X, key=lambda i: (_X[i] - x) ** 2 + 3 * (_Y[i] - y) ** 2)


def _spark(out: dict[int, RGB], style: _Fire, x: float, progress: float) -> None:
    """Draw a spark that has risen `progress` (0..1) of its way, plus its trail."""
    y = 0.75 - 0.9 * progress
    if progress < 0 or y < 0:
        return
    out[_nearest_key(x, y)] = style.sparks[min(2, int(progress * 3))]
    if progress > 0.12:
        below = _nearest_key(x, y + 0.2)
        if out.get(below) not in style.sparks:
            out[below] = style.trail


def _fire(style: _Fire) -> Callable[[T.Preset, float], dict[int, RGB]]:
    def frame(_preset: T.Preset, t: float) -> dict[int, RGB]:
        t *= style.pace
        out = {}
        for idx, y in _Y.items():
            col = min(_COLUMNS - 1, int(_X[idx] * _COLUMNS))
            row = round(y * 5)
            tongue = 0.5 + 0.5 * math.sin(t * 1.9 + col * 2.4) * math.sin(t * 0.7 + col * 1.3)
            flicker = 0.5 + 0.3 * math.sin(t * 7.3 + row * 2.1 + col) + 0.2 * math.sin(t * 12.7 + row * 5.3 + col * 3)
            reach = style.reach * (0.55 + 0.45 * tongue)         # this column's flame height
            heat = (y - (1 - reach)) / reach                     # 0 at the tip, 1 at the bottom
            if heat > 0:
                out[idx] = T.color_at(style.palette, heat ** 0.8 * (0.75 + 0.25 * flicker))
        for n in range(style.streams):                           # sparks, each at its own speed
            cycle, phase = divmod(t / (1.0 + 0.8 * _SEED[_nearest_key(n / style.streams, 1)][1])
                                  + n / style.streams, 1.0)
            rng = random.Random(n * 7919 + int(cycle))
            _spark(out, style, rng.random(), phase * (0.8 + 0.8 * rng.random()))
        slot = int(t / 3.0)                                      # now and then a burst of sparks
        rng = random.Random(99991 + slot)
        since = t - slot * 3.0 - 2.0 * rng.random()
        x = 0.15 + 0.7 * rng.random()
        for k in range(5):
            _spark(out, style, x + (k - 2) * 0.05, since * (1.0 + 0.15 * k))
        return out
    return frame


_EMBER = T.Preset("ember", "embers", [(0.0, (30, 0, 0)), (0.5, (120, 0, 0)), (0.85, (220, 20, 0)),
                                      (1.0, (255, 70, 0))])
_BLAZE = T.Preset("blaze", "white-hot", [(0.0, (180, 20, 0)), (0.35, (255, 100, 0)), (0.7, (255, 190, 0)),
                                         (1.0, (255, 250, 170))])
# tuned by eye on the keyboard: ember colors at an ember pace, flames high and full of sparks
fire = _fire(_Fire(_EMBER, ((255, 110, 0), (220, 40, 0), (150, 0, 0)), (70, 0, 0), 0.8, 0.6, 7))
blaze = _fire(_Fire(_BLAZE, ((255, 240, 120), (255, 170, 0), (255, 80, 0)), (150, 30, 0), 0.8, 0.9, 7))


@dataclass(frozen=True)
class Animation:
    name: str
    description: str
    frame: Callable[[T.Preset, float], dict[int, RGB]]
    uses_theme: bool = True
    direction: str | None = None  # how its colors change across the board (None: the theme's)
    bands: int | None = None      # groups along the direction (None: as many as fit)
    columns: int = 1              # and across the board, for colors that change both ways
    standout: int = STANDOUT      # 255: no key stands out, every key shows its band's color


_FIRE = {"uses_theme": False, "direction": "y", "bands": 6, "columns": _COLUMNS}

ANIMATIONS = [
    Animation("wave", "the theme flows across the board", wave),
    Animation("breathe", "the theme fades in and out", breathe),
    Animation("sparkle", "the theme glows while keys flash up one by one", sparkle),
    Animation("rainbow", "a rainbow moving from left to right", rainbow, uses_theme=False, direction="x",
              bands=11, standout=255),
    Animation("fire", "dark red flames rising and falling, sparks flying up", fire, **_FIRE),
    Animation("blaze", "a bright yellow fire full of sparks", blaze, **_FIRE),
]
ANIMATION_BY_NAME = {a.name: a for a in ANIMATIONS}


def frame(anim: Animation, preset: T.Preset, t: float) -> bytes:
    """The real-time frame (P.live_frame) of an animation at time t."""
    direction = anim.direction or preset.direction
    accents = _accent_groups(preset) if anim.uses_theme else ()
    return encode(anim.frame(preset, t), direction, accents, anim.bands, anim.columns, anim.standout)


def _accent_groups(preset: T.Preset) -> tuple[tuple[int, ...], ...]:
    by_color: dict[RGB, list[int]] = {}
    for key, rgb in preset.accents.items():
        by_color.setdefault(rgb, []).append(K.key_index(key))
    return tuple(tuple(keys) for keys in by_color.values())


def encode(colors: dict[int, RGB], direction: str, fixed: tuple[tuple[int, ...], ...] = (),
           bands: int | None = None, columns: int = 1, standout: int = STANDOUT) -> bytes:
    """A frame of colors -> a real-time frame (P.live_frame) that looks smooth.

    Every frame has to fit in BUDGET bytes, so keys share colors. They are put in
    fixed bands along `direction`, the same in every frame, and each band shows the
    average of its keys: had keys moved between groups from frame to frame, their
    colors would jump. The `fixed` key sets (a theme's accent keys) are groups of
    their own. Keys that differ a lot from their band join a band of a similar
    color, or else (a key flashing) share the SPARE groups. With `columns` the
    bands are also cut across the board, into cells.
    """
    lit = {i: c for i, c in colors.items() if any(c)}
    in_fixed = {i for keys in fixed for i in keys}
    n = bands or max(1, (BUDGET - len(_X)) // 4 - len(fixed) - SPARE)   # the same in every frame
    pos = T.positions(direction)
    cells: dict[tuple[int, int], list[int]] = {}
    for i in lit:
        if i not in in_fixed:
            cell = (min(n - 1, int(pos.get(i, 0.0) * n)), min(columns - 1, int(_X.get(i, 0.0) * columns)))
            cells.setdefault(cell, []).append(i)
    groups: dict[RGB, list[int]] = {}
    standouts: dict[RGB, list[int]] = {}
    for keys in [list(k) for k in fixed] + list(cells.values()):
        keys = [i for i in keys if i in lit]
        if not keys:
            continue
        mid = tuple(sorted(lit[i][ch] for i in keys)[len(keys) // 2] for ch in range(3))
        ref = min((lit[i] for i in keys), key=lambda c: _distance(c, mid))   # a typical key of the band
        inside = [i for i in keys if _distance(lit[i], ref) <= standout]
        for i in keys:
            if i not in inside:
                standouts.setdefault(lit[i], []).append(i)
        avg = tuple(round(sum(lit[i][ch] for i in inside) / len(inside)) for ch in range(3))
        groups.setdefault(avg, []).extend(inside)
    for c in list(standouts):                            # close to another band: join that one
        near = min(groups, key=lambda g: _distance(g, c))
        if _distance(near, c) <= standout:
            groups[near].extend(standouts.pop(c))
    room = max(1, (BUDGET - len(lit)) // 4 - len(groups))
    for c, keys in P.median_cut(standouts, room).items():
        groups.setdefault(c, []).extend(keys)
    if len(lit) + 4 * len(groups) > BUDGET:              # rare: merge the closest groups to fit
        groups = P.median_cut(groups, max(1, (BUDGET - len(lit)) // 4))
    return P.live_frame(groups)
