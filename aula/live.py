"""Animations played from the computer, frame by frame (real-time command 0x88).

Unlike the firmware effects these can show anything, e.g. a theme flowing across
the board. The keyboard only shows them while frames keep coming, so the GUI or
`aula animate` has to stay open; about 2 s after the last frame the keyboard goes
back to its own effect. Nothing is stored on the keyboard.

Every animation is a pure function of (theme, time, key presses), so the GUI can
draw the same frames it sends. Time runs faster or slower to change the speed;
key presses carry the time they happened at on that same clock.

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


def wave(preset: T.Preset, t: float, _presses=()) -> dict[int, RGB]:
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


def breathe(preset: T.Preset, t: float, _presses=()) -> dict[int, RGB]:
    """The whole theme fades in and out."""
    seen = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * t * 0.3))   # brightness as the eye sees it
    v = seen ** 2.2                                      # LED power: the eye is far more sensitive when dim
    return {idx: _scale(c, v) for idx, c in _theme(preset).items()}


_TWINKLE = [(0.15, _WHITE), (0.45, (110, 110, 110))]   # (seconds, color): bright, then half


def sparkle(preset: T.Preset, t: float, _presses=()) -> dict[int, RGB]:
    """The theme glows dimly while keys twinkle white, here and there."""
    out = {}
    for idx, c in _theme(preset).items():
        phase, rate = _SEED[idx]
        period = 2.5 + 3.5 * rate
        age = (t + phase * period) % period
        out[idx] = next((tw for end, tw in _TWINKLE if age < end), _scale(c, 0.3))
    return out


def rainbow(_preset: T.Preset, t: float, _presses=()) -> dict[int, RGB]:
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


def _fire(style: _Fire) -> Callable[..., dict[int, RGB]]:
    def frame(_preset: T.Preset, t: float, _presses=()) -> dict[int, RGB]:
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


# ------------------------------------------------------------- reacting to keys
Press = tuple[int, float]   # (matrix index, time of the press on the animation's clock)

_PITCH = 38.5                # key width on the drawing (keymap coordinates)
_CENTER = {idx: ((r[0] + r[2]) / 2 / _PITCH, (r[1] + r[3]) / 2 / _PITCH)
           for idx, _n, _l, r in K.KEYS if r != (0, 0, 0, 0)}
_DIST = {a: {b: math.dist(pa, pb) for b, pb in _CENTER.items()} for a, pa in _CENTER.items()}

PRESS_MEMORY = 40.0  # seconds of key presses an animation may still show (the heatmap's memory)
REST = 0.28     # how bright the theme glows while no key is pressed (0.2 too dark, 0.4 hid the rings)
LEVELS = 4      # lit keys are rounded to this many brightness steps: few colors per frame


def _step(x: float) -> float:
    return round(max(0.0, min(1.0, x)) * LEVELS) / LEVELS


def _hot(c: RGB, v: float) -> RGB:
    """A theme color lit up to step v (0..1): from just above the resting glow to full
    brightness, a little whiter at the top."""
    return _scale(_mix(c, _WHITE, 0.4 * v), REST + (1 - REST) * v)


def _resting(preset: T.Preset) -> dict[int, RGB]:
    return {idx: _scale(c, REST) for idx, c in _theme(preset).items()}


def _tones(preset: T.Preset) -> list[RGB]:
    """Four colors along the theme's gradient, darkest first: the colors keys light up in.
    Few shared tones keep a frame to few groups, so nothing gets mixed into a color the
    theme doesn't have."""
    return sorted((T.color_at(preset, i / 3) for i in range(4)), key=lambda c: 2 * c[0] + 5 * c[1] + c[2])


def _tone(preset: T.Preset, idx: int) -> RGB:
    """The theme's tone at a key (its gradient color, without the accent keys)."""
    return T.color_at(preset, round(T.positions(preset.direction)[idx] * 3) / 3)


def ripple(preset: T.Preset, t: float, presses=()) -> dict[int, RGB]:
    """Every key press sends a ring of its own color across the board."""
    out = _resting(preset)
    life, speed, width = 1.6, 7.0, 1.1              # seconds, keys per second, keys (~11 frames/s: slower looks smoother)
    best: dict[int, tuple[float, int]] = {}         # key -> (brightest ring on it, its origin)
    for origin, at in presses:
        age = t - at
        if not 0 <= age < life or origin not in _DIST:
            continue
        for idx, d in _DIST[origin].items():
            v = _step(max(0.0, 1 - abs(d - age * speed) / width) * (1 - age / life))
            if v > best.get(idx, (0.0, origin))[0]:
                best[idx] = (v, origin)
    for idx, (v, origin) in best.items():
        out[idx] = _hot(_tone(preset, origin), v)
    return out


def afterglow(preset: T.Preset, t: float, presses=()) -> dict[int, RGB]:
    """A pressed key flares up and fades back into the theme, warming its neighbours,
    so typing leaves a fading trail."""
    out = _resting(preset)
    glow: dict[int, float] = {}
    for origin, at in presses:
        age = t - at
        if not 0 <= age < 3.0 or origin not in _DIST:
            continue
        for idx, d in _DIST[origin].items():
            v = math.exp(-age * 1.1) * (1.0 if idx == origin else 0.4 * max(0.0, 1 - (d - 0.8) / 0.6))
            glow[idx] = max(glow.get(idx, 0.0), v)
    for idx, v in glow.items():
        if _step(v):
            out[idx] = _hot(_tone(preset, idx), _step(v))
    return out


def heatmap(preset: T.Preset, t: float, presses=()) -> dict[int, RGB]:
    """The keys you type most warm up through the theme's colors, and cool down slowly."""
    heat: dict[int, float] = {}
    for origin, at in presses:
        age = t - at
        if not 0 <= age < PRESS_MEMORY or origin not in _DIST:
            continue
        fade = math.exp(-age / 8.0)
        for idx, d in _DIST[origin].items():
            if d < 1.3:
                heat[idx] = heat.get(idx, 0.0) + fade * (1.0 if idx == origin else 0.25)
    out, tones = _resting(preset), _tones(preset)
    # warm to hot: the theme's three brighter tones at full brightness, then white-hot
    # (the darkest tone could look darker than the resting board)
    steps = [tones[1], tones[2], tones[3], _mix(tones[3], _WHITE, 0.5)]
    for idx, h in heat.items():
        level = min(LEVELS, int(h * 1.5))           # 1 press: step 1, about 3 recent ones: the top
        if level:
            out[idx] = steps[level - 1]
    return out


_DEMO = [K.key_index("space" if c == " " else c) for c in "the quick brown fox jumps over the lazy dog "]


def demo_presses(t: float, window: float = 40.0) -> list[Press]:
    """Pretend typing for previews: a key about every 0.3 s, spelling a sentence."""
    out = []
    for k in range(max(0, int((t - window) / 0.3)), int(t / 0.3) + 1):
        at = k * 0.3 + 0.12 * random.Random(k).random()
        if at <= t:
            out.append((_DEMO[k % len(_DEMO)], at))
    return out


@dataclass(frozen=True)
class Animation:
    name: str
    description: str
    frame: Callable[..., dict[int, RGB]]   # (theme, time, key presses) -> colors
    uses_theme: bool = True
    reactive: bool = False        # lights up the keys you press
    direction: str | None = None  # how its colors change across the board (None: the theme's)
    bands: int | None = None      # groups along the direction (None: as many as fit)
    columns: int = 1              # and across the board, for colors that change both ways
    standout: int = STANDOUT      # 255: no key stands out, every key shows its band's color
    spare: int = SPARE            # groups kept for keys that stand out


_FIRE = {"uses_theme": False, "direction": "y", "bands": 6, "columns": _COLUMNS}
# the resting theme needs few bands at its low brightness; the lit keys get the groups
_REACTIVE = {"reactive": True, "spare": 6}

ANIMATIONS = [
    Animation("wave", "the theme flows across the board", wave),
    Animation("breathe", "the theme fades in and out", breathe),
    Animation("sparkle", "the theme glows while keys flash up one by one", sparkle),
    Animation("rainbow", "a rainbow moving from left to right", rainbow, uses_theme=False, direction="x",
              bands=11, standout=255),
    Animation("fire", "dark red flames rising and falling, sparks flying up", fire, **_FIRE),
    Animation("blaze", "a bright yellow fire full of sparks", blaze, **_FIRE),
    Animation("ripple", "every key you press sends out a ring of its color", ripple, **_REACTIVE),
    Animation("afterglow", "pressed keys flare up and fade back slowly", afterglow, **_REACTIVE),
    Animation("heatmap", "the keys you type most warm up through the theme", heatmap, **_REACTIVE),
]
ANIMATION_BY_NAME = {a.name: a for a in ANIMATIONS}


def frame(anim: Animation, preset: T.Preset, t: float, presses=()) -> bytes:
    """The real-time frame (P.live_frame) of an animation at time t, given the
    key presses so far (Press tuples, on the same clock as t)."""
    direction = anim.direction or preset.direction
    accents = _accent_groups(preset) if anim.uses_theme else ()
    if anim.reactive:
        return layered(anim.frame(preset, t, presses), _resting(preset), direction, accents)
    return encode(anim.frame(preset, t, presses), direction, accents, anim.bands, anim.columns,
                  anim.standout, anim.spare)


def _accent_groups(preset: T.Preset) -> tuple[tuple[int, ...], ...]:
    by_color: dict[RGB, list[int]] = {}
    for key, rgb in preset.accents.items():
        by_color.setdefault(rgb, []).append(K.key_index(key))
    return tuple(tuple(keys) for keys in by_color.values())


def encode(colors: dict[int, RGB], direction: str, fixed: tuple[tuple[int, ...], ...] = (),
           bands: int | None = None, columns: int = 1, standout: int = STANDOUT,
           spare: int = SPARE) -> bytes:
    """A frame of colors -> a real-time frame (P.live_frame) that looks smooth.

    Every frame has to fit in BUDGET bytes, so keys share colors. They are put in
    fixed bands along `direction`, the same in every frame, and each band shows the
    average of its keys: had keys moved between groups from frame to frame, their
    colors would jump. The `fixed` key sets (a theme's accent keys) are groups of
    their own. Keys that differ a lot from their band join a band of a similar
    color, or else (a key flashing) share the `spare` groups. With `columns` the
    bands are also cut across the board, into cells.
    """
    lit = {i: c for i, c in colors.items() if any(c)}
    in_fixed = {i for keys in fixed for i in keys}
    n = bands or max(1, (BUDGET - len(_X)) // 4 - len(fixed) - spare)   # the same in every frame
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
        if inside:
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


# ------------------------------------------------- frames that survive lost packets
LIT_PACKETS = 4      # packets for the lit keys, after the resting board
REST_BANDS = 5       # the resting board is dim: a few bands of the theme are enough


def layered(colors: dict[int, RGB], rest: dict[int, RGB], direction: str,
            fixed: tuple[tuple[int, ...], ...] = ()) -> bytes:
    """A frame for animations that light up keys over a resting board.

    The keyboard assembles a frame from its packets by index and drops it until
    all have come (tested). So after a lost packet, the next frame's packet fills
    the gap and the keyboard shows a mix of two frames; if their layouts differ,
    bytes are read in the wrong place and keys show colors that were never sent.
    Typing makes packets get lost. So here every packet stands on its own: it is
    exactly CHUNK bytes of whole groups, and every frame of a theme has the same
    number of packets. First the resting board, the same bytes in every frame (so
    it may run across packets, as long as it ends with one), then the lit keys,
    which override it (a later group wins, tested). Any mix of packets from two
    frames then reads as a valid frame.
    """
    resting, shown = _resting_layer(rest, direction, fixed)
    base_bytes = b"".join(bytes([*c, len(keys), *keys]) for c, keys in resting)
    gap = -len(base_bytes) % P.CHUNK
    base_bytes += _filler(shown)(gap - 4) if gap >= 5 else _fill(shown, gap + P.CHUNK) if gap else b""
    base = [base_bytes[n:n + P.CHUNK] for n in range(0, len(base_bytes), P.CHUNK)]
    lit: dict[RGB, list[int]] = {}
    for i, c in sorted(colors.items()):
        if i in rest and c != rest[i]:
            lit.setdefault(c, []).append(i)
    final = dict(shown)
    room = 2 * LIT_PACKETS                               # at most two groups per packet
    while True:
        layers = P.median_cut(lit, room)
        for c, keys in layers.items():
            final.update((i, c) for i in keys)
        top = _pack(list(layers.items()), final)
        if len(top) <= LIT_PACKETS:
            filler = _filler(final)
            return b"".join(base + top + [filler(5) + filler(1)] * (LIT_PACKETS - len(top)))
        final = dict(shown)
        if room > 1:                                     # too much: fewer colors
            room -= 1
        else:                                            # still too much: the faintest lit key rests
            c = min(lit, key=sum)
            lit[c].pop()
            if not lit[c]:
                del lit[c]


def _resting_layer(rest, direction, fixed):
    """The resting board as groups: the accent sets, then the rest in REST_BANDS bands
    along the direction, each shown in its keys' average color."""
    pos = T.positions(direction)
    in_fixed = {i for keys in fixed for i in keys}
    order = sorted((i for i in rest if i not in in_fixed), key=lambda i: (pos.get(i, 0.0), i))
    size = -(-len(order) // REST_BANDS)
    groups, shown = [], {}
    for keys in [list(k) for k in fixed] + [order[n:n + size] for n in range(0, len(order), size)]:
        c = tuple(round(sum(rest[i][ch] for i in keys) / len(keys)) for ch in range(3))
        groups.append((c, keys))
        shown.update((i, c) for i in keys)
    return groups, shown


def _filler(final: dict[int, RGB]):
    """Groups that restate keys in the color they show anyway: harmless anywhere."""
    by_color: dict[RGB, list[int]] = {}
    for i, c in final.items():
        by_color.setdefault(c, []).append(i)
    c, keys = max(by_color.items(), key=lambda ck: len(ck[1]))
    return lambda k: bytes([*c, k, *keys[:k]])


def _fill(final: dict[int, RGB], length: int) -> bytes:
    """Exactly `length` (>= 10) bytes of harmless groups: two, if one color is too short."""
    filler = _filler(final)
    first = min(length - 9, 4 + 10)                      # leave at least 5 for the second
    return filler(first - 4) + filler(length - first - 4) if length - first >= 5 else filler(length - 4)


def _pack(groups, final: dict[int, RGB]) -> list[bytes]:
    """(color, keys) groups as packets of exactly CHUNK (14) bytes, each starting with
    a group: one group of 10 keys, or two groups of 6 keys between them (nothing
    else adds up to 14). A color may be split over several groups; gaps are filled."""
    out, rest = [], []
    for c, keys in groups:
        keys = list(keys)
        while len(keys) >= 10:
            out.append(bytes([*c, 10, *keys[:10]]))
            keys = keys[10:]
        if keys:
            rest.append([c, keys])
    filler = _filler(final)

    def take(item, k):
        keys, item[1] = item[1][:k], item[1][k:]
        if not item[1]:
            rest.remove(item)
        return bytes([*item[0], k, *keys])

    while rest:
        rest.sort(key=lambda item: -len(item[1]))        # pair the biggest leftovers first
        first = take(rest[0], min(5, len(rest[0][1])))
        need = 6 - first[3]
        nxt = next((item for item in rest if len(item[1]) >= need), None)
        out.append(first + (take(nxt, need) if nxt else filler(need)))
    return out
