"""Approximate, animated previews of the firmware lighting effects.

These imitate what each effect looks like on the keyboard (observed by eye); they
are not exact copies of the firmware. Pure functions of (LED settings, time), so
the GUI only has to call frame() on a timer.
"""

import colorsys
import math
import random

from . import keymap as K
from . import protocol as P

RGB = tuple[int, int, int]

# Factory colors 0-6 (the keyboard's palettes, command 0x49, can change them per effect)
PALETTE = P.DEFAULT_PALETTE

REACTIVE = {4, 7, 12}  # these react to key presses; the preview plays a demo

_X0, _Y0, _X1, _Y1 = 30, 30, 630, 263
# (index, x 0..1, y 0..1) for every key that has a position (the knob has no LED)
_POS = [(idx, ((r[0] + r[2]) / 2 - _X0) / (_X1 - _X0), ((r[1] + r[3]) / 2 - _Y0) / (_Y1 - _Y0))
        for idx, _n, _l, r in K.KEYS if r != (0, 0, 0, 0)]
_ROWS = sorted({round(y, 2) for _, _, y in _POS})
# snake path: rows top to bottom, alternating direction
_SNAKE = [idx for i, row in enumerate(_ROWS)
          for idx, x, y in sorted((p for p in _POS if round(p[2], 2) == row),
                                  key=lambda p: p[1], reverse=bool(i % 2))]


def _hue(h: float, v: float = 1.0) -> RGB:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, max(0.0, min(1.0, v)))
    return round(r * 255), round(g * 255), round(b * 255)


def _scale(c: RGB, v: float) -> RGB:
    v = max(0.0, min(1.0, v))
    return tuple(round(ch * v) for ch in c)


def _demo_origin(t: float, period: float, salt: int):
    """A pseudo-random key position that changes every `period` seconds."""
    n = int(t // period)
    rng = random.Random(n * 7919 + salt)
    _, x, y = rng.choice(_POS)
    return x, y, (t % period) / period


def is_animated(led: P.LedConfig) -> bool:
    return led.effect not in (1, P.EFFECT_BY_NAME["custom"].hw) and 1 <= led.effect <= P.LED_SLOTS


def frame(led: P.LedConfig, t: float, palette: bytes | None = None) -> dict[int, RGB] | None:
    """Colors for every key at time t (seconds). None means: show the custom table.

    `palette` is the keyboard's effect palettes (0x49), for effects given their own colors.
    """
    hw = led.effect
    if hw == P.EFFECT_BY_NAME["custom"].hw:
        return None
    if not 1 <= hw <= P.LED_SLOTS:
        return {}
    e = P.EFFECT_BY_HW.get(hw)
    slot = led.slot(hw)
    k = max(0.15, slot.brightness / 9)
    sp = 0.4 + 0.4 * slot.speed
    single = e is not None and e.color and slot.color < len(PALETTE)
    base = PALETTE[slot.color] if single else None
    if single and palette is not None and hw < P.PALETTE_COUNT:
        base = P.palette_color(palette, hw, slot.color)

    def color(x: float, v: float = 1.0) -> RGB:
        """The effect's color at horizontal position x, at intensity v."""
        if base is not None:
            return _scale(base, v * k)
        return _hue(x * 0.8 + t * 0.05 * sp, v * k)

    out: dict[int, RGB] = {}
    if hw == 1:                                   # static
        for idx, x, _ in _POS:
            out[idx] = color(x)
    elif hw == 2:                                 # breathing
        v = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * t * 0.4 * sp))
        for idx, x, _ in _POS:
            out[idx] = color(x, v)
    elif hw == 3:                                 # spectrum: whole board, hue cycles while breathing
        v = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * t * 0.4 * sp))
        c = _hue(t * 0.08 * sp, v * k)
        out = {idx: c for idx, _, _ in _POS}
    elif hw in (4, 7):                            # ripple along the row / over the whole board
        ox, oy, phase = _demo_origin(t, 2.2 / sp, hw)
        radius = phase * 1.4
        for idx, x, y in _POS:
            if hw == 4 and abs(y - oy) > 0.05:
                out[idx] = (0, 0, 0)
                continue
            d = abs(x - ox) if hw == 4 else math.hypot(x - ox, (y - oy) * 0.4)
            ring = max(0.0, 1 - abs(d - radius) / 0.12) * (1 - phase)
            out[idx] = color(x, ring)
    elif hw == 12:                                # reactive: the pressed key lights up and fades
        for idx, x, _ in _POS:
            out[idx] = (0, 0, 0)
        for salt in range(3):
            ox, oy, phase = _demo_origin(t + salt * 0.4, 1.2 / sp, 100 + salt)
            idx = min(_POS, key=lambda p: (p[1] - ox) ** 2 + (p[2] - oy) ** 2)[0]
            out[idx] = color(ox, 1 - phase)
    elif hw in (5, 8):                            # raindrops / twinkle: random keys fade in and out
        rate = 0.5 * sp if hw == 5 else 0.3 * sp
        for idx, x, _ in _POS:
            rng = random.Random(idx * 31 + hw)
            period = rng.uniform(2.0, 5.0)
            p = ((t * rate * 2 + rng.random() * period) % period) / period
            v = max(0.0, 1 - p * 4) if hw == 5 else max(0.0, math.sin(p * math.pi) * 2 - 1)
            out[idx] = color(x, v)
    elif hw == 6:                                 # slow wave, left to right
        for idx, x, _ in _POS:
            out[idx] = color(x, 0.15 + 0.85 * (0.5 + 0.5 * math.cos(2 * math.pi * (x - t * 0.15 * sp))))
    elif hw == 10:                                # snake
        head = t * 6 * sp
        n = len(_SNAKE)
        for i, idx in enumerate(_SNAKE):
            behind = (head - i) % n
            x = next(p[1] for p in _POS if p[0] == idx)
            out[idx] = color(x, max(0.0, 1 - behind / 8))
    elif hw == 11:                                # stream, left to right
        for idx, x, _ in _POS:
            out[idx] = color(x, ((x * 3 - t * 0.6 * sp) % 1.0) ** 2)
    elif hw == 13:                                # center wave: from the middle to both sides
        for idx, x, _ in _POS:
            d = abs(x - 0.5) * 2
            out[idx] = color(x, 0.1 + 0.9 * (0.5 + 0.5 * math.cos(2 * math.pi * (d * 1.5 - t * 0.4 * sp))))
    elif hw == 15:                                # rainbow wheel: hue rotates around the center
        for idx, x, y in _POS:
            a = math.atan2((y - 0.5) * 0.4, x - 0.5) / (2 * math.pi)
            out[idx] = _hue(a - t * 0.12 * sp, k)
    elif hw == 16:                                # waterfall: rainbow flowing downwards
        for idx, x, y in _POS:
            out[idx] = _hue(y * 0.6 - t * 0.15 * sp, k)
    elif hw == 17:                                # fast flicker from the middle outwards
        for idx, x, _ in _POS:
            d = abs(x - 0.5) * 2
            on = math.sin(2 * math.pi * (t * 3 * sp - d * 2)) > 0.3
            out[idx] = color(x, 1.0 if on else 0.05)
    else:                                         # unknown firmware effect
        for idx, x, _ in _POS:
            out[idx] = color(x, 0.3)
    return out
