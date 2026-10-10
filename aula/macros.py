"""Macro storage format (command 0x03 / 0x43), from the official app's
StMacro_To_HdMacro and checked against the keyboard's factory macro.

Store (first 512-byte block):
    header   one [address u16, size u16] entry per macro (little endian);
             the first address equals the header size, so it gives the count
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
MAX_DELAY = 0xFFFFF
KIND_KEY, KIND_MOD, KIND_MOUSE = 0, 1, 2

MOD_CODES = {"lctrl": 0xE0, "lshift": 0xE1, "lalt": 0xE2, "lwin": 0xE3,
             "rctrl": 0xE4, "rshift": 0xE5, "ralt": 0xE6, "rwin": 0xE7}
MOD_ALIASES = {"ctrl": "lctrl", "shift": "lshift", "alt": "lalt", "win": "lwin",
               "super": "lwin", "altgr": "ralt"}

REPEAT_TIMES, REPEAT_HOLD, REPEAT_UNTIL_KEY = 1, 2, 4
MACRO_ENTRY = 0x03

# US layout characters for text:… steps -> (HID usage, needs shift)
_SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
            "(": "9", ")": "0", "_": "minus", "+": "equal", "{": "lbracket", "}": "rbracket",
            "|": "backslash", ":": "semicolon", '"': "quote", "~": "grave", "<": "comma",
            ">": "period", "?": "slash"}
_PLAIN = {" ": "space", "-": "minus", "=": "equal", "[": "lbracket", "]": "rbracket",
          "\\": "backslash", ";": "semicolon", "'": "quote", "`": "grave", ",": "comma",
          ".": "period", "/": "slash", "\n": "enter", "\t": "tab"}


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
    header = bytearray()
    bodies = bytearray()
    addr = 4 * len(macros)
    for m in macros:
        body = m.encode()
        header += addr.to_bytes(2, "little") + len(body).to_bytes(2, "little")
        bodies += body
        addr += len(body)
    data = bytes(header + bodies)
    if len(data) > STORE_LEN:
        raise ValueError(f"macros need {len(data)} bytes, the keyboard holds {STORE_LEN}")
    return data + bytes(STORE_LEN - len(data))


def macro_entry(index: int, mode: int = REPEAT_TIMES, count: int = 1) -> bytes:
    return bytes([MACRO_ENTRY, mode, max(1, min(count, 255)) if mode == REPEAT_TIMES else 1, index])


# ---------------------------------------------------------------- steps
def _tap(code_kind: list[tuple[int, int]], delay: int) -> list[Event]:
    downs = [Event(k, c, True, delay) for k, c in code_kind]
    ups = [Event(k, c, False, delay) for k, c in reversed(code_kind)]
    return downs + ups


def _combo(step: str, delay: int) -> list[Event]:
    keys = []
    for part in step.lower().split("+"):
        part = MOD_ALIASES.get(part, part)
        part = K.TR_ALIASES.get(part, part)
        if part in MOD_CODES:
            keys.append((KIND_MOD, MOD_CODES[part]))
        elif part in K.HID:
            keys.append((KIND_KEY, K.HID[part]))
        else:
            raise ValueError(f"unknown key in macro step: {part!r}")
    return _tap(keys, delay)


def _text(text: str, delay: int) -> list[Event]:
    events = []
    for ch in text:
        if ch.isascii() and ch.isalpha():
            key, shift = ch.lower(), ch.isupper()
        elif ch.isdigit():
            key, shift = ch, False
        elif ch in _PLAIN:
            key, shift = _PLAIN[ch], False
        elif ch in _SHIFTED:
            key, shift = _SHIFTED[ch], True
        else:
            raise ValueError(f"text steps support US-layout ASCII only, got {ch!r}")
        keys = [(KIND_MOD, MOD_CODES["lshift"])] if shift else []
        events += _tap(keys + [(KIND_KEY, K.HID[key])], delay)
    return events


def parse_steps(steps: list[str], delay: int = 20) -> list[Event]:
    """Turn steps like 'ctrl+c', 'wait:100', 'text:hello' into events."""
    events: list[Event] = []
    for step in steps:
        if step.startswith("wait:"):
            if not events:
                raise ValueError("a macro can't start with a wait")
            events[-1].delay += int(step[5:])
        elif step.startswith("text:"):
            events += _text(step[5:], delay)
        else:
            events += _combo(step, delay)
    if not events:
        raise ValueError("a macro needs at least one step")
    return events
