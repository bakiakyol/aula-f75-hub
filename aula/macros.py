"""Macro storage format (command 0x03 / 0x43), from the official app's
StMacro_To_HdMacro and checked against the keyboard's factory macro.

Store (first 512-byte block):
    header   one [address u16, size u16] entry per macro (little endian);
             the first address equals the header size, so it gives the count
             (bytes 126-127 get overwritten with 5A A5 by the firmware)
    macro    [name length in bytes] + name + events (4 bytes each)

Event:
    byte 0   (kind << 4) | delay bits 19..16, plus 0x80 for a release
             kind: 0 key (HID usage), 1 modifier (0xE0-0xE7), 2 mouse button,
                   3 / 4 mouse move X / Y, 5 wheel
    byte 1-2 delay bits 15..0 (milliseconds until the next event)
    byte 3   code

Keymap entry for a macro key: [0x03, repeat mode, repeat count, macro index]
    repeat mode: 1 = run `count` times, 2 = repeat while held,
                 4 = repeat until any key is pressed
"""

from dataclasses import dataclass, field

from . import keymap as K

STORE_LEN = 512
# The firmware writes 5A A5 over bytes 126-127 of the store (as at the end of the
# 128-byte LED block), so no macro may cover them.
RESERVED = (126, 128)
MAX_DELAY = 0xFFFFF
KIND_KEY, KIND_MOD, KIND_MOUSE = 0, 1, 2

MOD_CODES = {"lctrl": 0xE0, "lshift": 0xE1, "lalt": 0xE2, "lwin": 0xE3,
             "rctrl": 0xE4, "rshift": 0xE5, "ralt": 0xE6, "rwin": 0xE7}
MOD_ALIASES = {"ctrl": "lctrl", "shift": "lshift", "alt": "lalt", "win": "lwin",
               "super": "lwin", "altgr": "ralt"}

REPEAT_TIMES, REPEAT_HOLD, REPEAT_UNTIL_KEY = 1, 2, 4
MACRO_ENTRY = 0x03

# Characters a text:… step can type. The keyboard sends key positions, and the
# computer's layout turns them into characters, so each layout has its own table:
# key name -> characters on that key (plain, with Shift, with AltGr)
_US_KEYS = {
    "1": "1!", "2": "2@", "3": "3#", "4": "4$", "5": "5%", "6": "6^", "7": "7&", "8": "8*",
    "9": "9(", "0": "0)", "minus": "-_", "equal": "=+", "lbracket": "[{", "rbracket": "]}",
    "backslash": "\\|", "semicolon": ";:", "quote": "'\"", "grave": "`~", "comma": ",<",
    "period": ".>", "slash": "/?", "space": " ", "enter": "\n", "tab": "\t",
    **{c: c + c.upper() for c in "abcdefghijklmnopqrstuvwxyz"},
}
_TR_Q_KEYS = {  # xkb "tr" (Turkish Q)
    **_US_KEYS,
    "grave": '"é<', "1": "1!>", "2": "2'£", "3": "3^#", "4": "4+$", "5": "5%½", "6": "6&¾",
    "7": "7/{", "8": "8([", "9": "9)]", "0": "0=}", "minus": "*?\\", "equal": "-_|",
    "q": "qQ@", "e": "eE€", "t": "tT₺", "u": "uUû", "i": "ıIî", "o": "oOô", "a": "aAâ",
    "s": "sSß", "lbracket": "ğĞ", "rbracket": "üÜ~", "semicolon": "şŞ", "quote": "iİ",
    "backslash": ",;`", "iso_backslash": "<>|", "comma": "öÖ", "period": "çÇ", "slash": ".:",
}
# macOS: Apple's "Turkish Q - PC" is the PC layout, except that its Option level
# isn't known well enough here, so it is left out. Apple's own "Turkish Q" has the
# Turkish letters in the PC places, but its punctuation is elsewhere: letters,
# digits and white space only.
_TR_MAC_PC_KEYS = {key: chars[:2] for key, chars in _TR_Q_KEYS.items()}
_TR_MAC_KEYS = {
    **{c: c + c.upper() for c in "abcdefghjklmnopqrstuvwxyz"}, "i": "ıI", "quote": "iİ",
    "lbracket": "ğĞ", "rbracket": "üÜ", "semicolon": "şŞ", "comma": "öÖ", "period": "çÇ",
    **{str(d): str(d) for d in range(10)}, "space": " ", "enter": "\n", "tab": "\t",
}
LAYOUTS = {"us": "English (US)", "tr": "Turkish Q", "tr_mac_pc": "Turkish Q - PC (Mac)",
           "tr_mac": "Turkish Q (Mac, letters only)"}


def _char_table(keys: dict[str, str]) -> dict[str, tuple[str, list[str]]]:
    """character -> (key name, modifiers); the simplest way to type it wins."""
    table: dict[str, tuple[str, list[str]]] = {}
    for level, mods in enumerate(([], ["lshift"], ["ralt"])):
        for key, chars in keys.items():
            if level < len(chars):
                table.setdefault(chars[level], (key, mods))
    return table


_TEXT_KEYS = {"us": _US_KEYS, "tr": _TR_Q_KEYS, "tr_mac_pc": _TR_MAC_PC_KEYS, "tr_mac": _TR_MAC_KEYS}
_CHARS = {name: _char_table(keys) for name, keys in _TEXT_KEYS.items()}


def detect_layout() -> str:
    """'tr' when the computer uses the Turkish Q layout, otherwise 'us'."""
    from . import backends
    return backends.detect_layout()


@dataclass
class Event:
    kind: int
    code: int
    down: bool
    delay: int = 20  # ms until the next event

    def encode(self) -> bytes:
        d = max(0, min(self.delay, MAX_DELAY))
        b0 = (self.kind << 4) | ((d >> 16) & 0x0F)
        if not self.down and self.kind in (KIND_KEY, KIND_MOD, KIND_MOUSE):
            b0 |= 0x80
        return bytes([b0, (d >> 8) & 0xFF, d & 0xFF, self.code])

    @classmethod
    def decode(cls, b: bytes) -> "Event":
        return cls(kind=(b[0] >> 4) & 0x07, code=b[3], down=not b[0] & 0x80,
                   delay=((b[0] & 0x0F) << 16) | (b[1] << 8) | b[2])

    def describe(self) -> str:
        if self.kind == KIND_MOD:
            name = next((n for n, c in MOD_CODES.items() if c == self.code), f"0x{self.code:02x}")
        elif self.kind == KIND_KEY:
            name = next((n for n, c in K.HID.items() if c == self.code), f"0x{self.code:02x}")
        else:
            name = f"kind{self.kind}:0x{self.code:02x}"
        return f"{name}{'↓' if self.down else '↑'}{self.delay}ms"


@dataclass
class Macro:
    name: str
    events: list[Event] = field(default_factory=list)
    raw_name: bytes | None = None  # name bytes as read from the keyboard, kept unchanged

    def _name_bytes(self) -> bytes:
        if self.raw_name is not None and _decode_name(self.raw_name) == self.name:
            return self.raw_name
        return self.name.encode("utf-16-le")[:60]

    def encode(self) -> bytes:
        n = self._name_bytes()
        return bytes([len(n)]) + n + b"".join(e.encode() for e in self.events)


def _decode_name(raw: bytes) -> str:
    if raw and all(0x20 <= c < 0x7F for c in raw):  # the factory macro uses plain ASCII
        return raw.decode("ascii")
    return raw.decode("utf-16-le", errors="replace")


def parse_store(raw: bytes) -> list[Macro]:
    first = int.from_bytes(raw[0:2], "little")
    if first == 0 or first % 4 or first > len(raw):
        return []
    macros = []
    for i in range(first // 4):
        addr = int.from_bytes(raw[4 * i:4 * i + 2], "little")
        size = int.from_bytes(raw[4 * i + 2:4 * i + 4], "little")
        body = raw[addr:addr + size]
        if not body:
            break
        nlen = body[0]
        events = body[1 + nlen:]
        name = bytes(body[1:1 + nlen])
        macros.append(Macro(_decode_name(name),
                            [Event.decode(events[j:j + 4]) for j in range(0, len(events) - 3, 4)],
                            raw_name=name))
    return macros


def build_store(macros: list[Macro]) -> bytes:
    """Lay the macros out by address, keeping them clear of the bytes the firmware
    overwrites (a macro that would cross them starts after them)."""
    data = bytearray(4 * len(macros))
    if len(data) > RESERVED[0]:
        raise ValueError("too many macros")
    for i, m in enumerate(macros):
        body = m.encode()
        addr = len(data)
        if addr < RESERVED[1] and addr + len(body) > RESERVED[0]:
            addr = RESERVED[1]
            data += bytes(addr - len(data))
        data[4 * i:4 * i + 4] = addr.to_bytes(2, "little") + len(body).to_bytes(2, "little")
        data += body
    if len(data) > STORE_LEN:
        raise ValueError(f"macros need {len(data)} bytes, the keyboard holds {STORE_LEN}")
    return bytes(data) + bytes(STORE_LEN - len(data))


def macro_entry(index: int, mode: int = REPEAT_TIMES, count: int = 1) -> bytes:
    return bytes([MACRO_ENTRY, mode, max(1, min(count, 255)) if mode == REPEAT_TIMES else 1, index])


# ---------------------------------------------------------------- steps
def _tap(code_kind: list[tuple[int, int]], delay: int) -> list[Event]:
    downs = [Event(k, c, True, delay) for k, c in code_kind]
    ups = [Event(k, c, False, delay) for k, c in reversed(code_kind)]
    return downs + ups


def _key(name: str) -> tuple[int, int]:
    name = MOD_ALIASES.get(name, name)
    name = K.TR_ALIASES.get(name, name)
    if name in MOD_CODES:
        return KIND_MOD, MOD_CODES[name]
    if name in K.HID:
        return KIND_KEY, K.HID[name]
    raise ValueError(f"unknown key in macro step: {name!r}")


def _combo(step: str, delay: int) -> list[Event]:
    return _tap([_key(part) for part in step.lower().split("+")], delay)


def _text(text: str, delay: int, layout: str) -> list[Event]:
    chars = _CHARS[layout]
    events = []
    for ch in text:
        if ch not in chars:
            raise ValueError(f"text steps can't type {ch!r} with the {LAYOUTS[layout]} layout")
        key, mods = chars[ch]
        keys = [(KIND_MOD, MOD_CODES[m]) for m in mods]
        events += _tap(keys + [(KIND_KEY, K.HID[key])], delay)
    return events


def parse_steps(steps: list[str], delay: int = 20, layout: str = "us") -> list[Event]:
    """Turn steps like 'ctrl+c', 'wait:100', 'text:hello', 'down:shift' into events.

    `layout` is the computer's keyboard layout ("us" or "tr"): text steps are
    typed with the keys that give those characters there.
    """
    events: list[Event] = []
    for step in steps:
        if step.startswith("wait:"):
            if not events:
                raise ValueError("a macro can't start with a wait")
            events[-1].delay += int(step[5:])
        elif step.startswith("text:"):
            events += _text(step[5:], delay, layout)
        elif step.startswith(("down:", "up:")):
            action, _, name = step.partition(":")
            events.append(Event(*_key(name.strip().lower()), action == "down", delay))
        else:
            events += _combo(step, delay)
    if not events:
        raise ValueError("a macro needs at least one step")
    return events


# ------------------------------------------------------------ recording
_SHORT = {"lctrl": "ctrl", "lshift": "shift", "lalt": "alt", "lwin": "win", "ralt": "altgr"}
_LEVEL_MODS = ((), ("lshift",), ("ralt",))
PAUSE_MIN = 100  # ms; shorter gaps between recorded steps aren't kept as waits
HOLD_MIN = 300  # ms; a key held this long while others are pressed is a real hold


def _combos(rec: list[tuple[str, bool, int]]) -> list[tuple[list[str], int, int]] | None:
    """Group a recording into key combos (the modifiers held when a key goes
    down, plus that key), as (key names, start ms, end ms), in press order.

    Fast typing overlaps keys (the next one goes down before the last one is
    up); that still counts as separate taps. None when a key is really held
    (HOLD_MIN ms or more) while others are pressed, which only down:/up: can say.
    """
    out: list[tuple[list[str], int, int]] = []
    held: list[list] = []  # [modifier, used in a combo yet, pressed at]
    pressed: dict[str, tuple[int, int]] = {}  # key -> (index in rec, index in out)
    for i, (name, down, t) in enumerate(rec):
        if name in MOD_CODES:
            mod = next((h for h in held if h[0] == name), None)
            if down == (mod is not None):
                return None
            if down:
                held.append([name, False, t])
            else:
                if not mod[1]:  # pressed and let go on its own, e.g. the Win key
                    alone = [h for h in held if not h[1]]
                    out.append(([h[0] for h in alone], alone[0][2], t))
                    for h in alone:
                        h[1] = True
                held.remove(mod)
        elif down:
            if name in pressed:
                return None
            pressed[name] = (i, len(out))
            out.append(([h[0] for h in held] + [name], t, t))
            for h in held:
                h[1] = True
        else:
            if name not in pressed:
                return None
            j, k = pressed.pop(name)
            names, start, _ = out[k]
            if t - start >= HOLD_MIN and any(d for _n, d, _t in rec[j + 1:i]):
                return None
            out[k] = (names, start, t)
    return out


def steps_from_recording(rec: list[tuple[str, bool, int]], layout: str = "us",
                         pauses: bool = False) -> list[str]:
    """Turn recorded key events (key name, pressed, time in ms) into steps.

    Typed characters become text: steps for `layout`, the rest key combos.
    Keys held down across others fall back to down:/up: steps. With `pauses`, gaps
    of PAUSE_MIN ms or more become wait: steps.
    """
    chars = {(key, mods): chars[level]
             for key, chars in _TEXT_KEYS[layout].items()
             for level, mods in enumerate(_LEVEL_MODS) if level < len(chars)}
    groups = _combos(rec)
    if groups is None:
        steps = [(f"{'down' if d else 'up'}:{_SHORT.get(n, n)}", t, t, None) for n, d, t in rec]
    else:
        steps = []
        for names, start, end in groups:
            mods = tuple(sorted("lshift" if n == "rshift" else n for n in names[:-1]))
            ch = chars.get((names[-1], mods))
            steps.append(("+".join(_SHORT.get(n, n) for n in names), start, end,
                          ch if ch not in (None, "\n", "\t") else None))
    out: list[str] = []
    text = ""
    prev_end = None
    for step, start, end, ch in steps:
        pause = start - prev_end if pauses and prev_end is not None else 0
        if text and (ch is None or pause >= PAUSE_MIN):
            out += _text_steps(text)
            text = ""
        if pause >= PAUSE_MIN:
            out.append(f"wait:{round(pause, -1)}")
        if ch is not None:
            text += ch
        else:
            out.append(step)
        prev_end = end
    return out + _text_steps(text)


def _text_steps(text: str) -> list[str]:
    """A text: step, with spaces at either end as their own steps (the step
    editor trims lines)."""
    if not text:
        return []
    body = text.strip(" ")
    lead = len(text) - len(text.lstrip(" "))
    trail = len(text) - len(text.rstrip(" ")) if body else 0
    return ["space"] * lead + ([f"text:{body}"] if body else []) + ["space"] * trail
