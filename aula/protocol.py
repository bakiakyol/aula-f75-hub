"""AULA F75 wireless (2.4G dongle / Bluetooth) configuration protocol.

Recovered by static analysis of the official app (OemDrv.exe, class CDev3632)
and verified on real hardware. Details: docs/protocol.md

Packet (20 bytes, HID report 0x13):
    [0]    0x13           report id
    [1]    command        read commands = write command | 0x40
    [2]    packet count   in replies, bit 7 (0x80) = error
    [3]    packet index
    [4]    (sub << 4) | payload length (max 14)
    [5:19] payload
    [19]   sum of the first 19 bytes & 0xFF
"""

from dataclasses import dataclass

from .keymap import MATRIX_LEN

REPORT_ID = 0x13
PACKET_LEN = 20
CHUNK = 14

CMD_SET_MATRIX = 0x01   # keymap, sub = layer (0 base, 1 Fn)
CMD_SET_CUSTOM = 0x02   # per-key RGB table (custom / "Self-define" effect)
CMD_SET_MACRO = 0x03
CMD_SET_LED = 0x04      # effect / brightness / speed / color
CMD_RESET = 0x06        # factory reset (no reply)
CMD_SET_PALETTE = 0x09  # per-effect 7-color palettes
CMD_PROFILE = 0x0A
CMD_LIVE = 0x88         # real-time frame: not acknowledged, not stored (see live_frame)
READ = 0x40

LIVE_KEYS = 1           # sub of CMD_LIVE: per-key colors as color groups
LIVE_MAX = 200          # longest frame the official app sends
LIVE_GAP = 0.005        # s between packets: closer together the keyboard drops frames (tested)

LED_LEN = 128
LED_MAGIC = b"\x5a\xa5"
LED_EFFECT_OFFSET = 10
LED_WIN_LOCK_OFFSET = 15    # 1 = Windows key disabled (Fn+Win)
LED_SIDE_MODE_OFFSET = 18   # white bar next to Esc (Fn+Left Shift cycles it)
LED_KNOB_MODE_OFFSET = 26   # knob function (long-press the knob to toggle)
LED_OS_MODE_OFFSET = 27     # Fn+W / Fn+Q / Fn+E
LED_SLEEP_OFFSET = 24       # wireless sleep timer in units of 30 s, 0 = never
LED_SLOTS_OFFSET = 58
LED_SLOTS = 34
CUSTOM_LEN = MATRIX_LEN * 3
MATRIX_BYTES = MATRIX_LEN * 4


def checksum(b: bytes) -> int:
    return sum(b[:19]) & 0xFF


def build_packet(cmd: int, total: int, index: int, sub: int, chunk: bytes) -> bytes:
    if len(chunk) > CHUNK:
        raise ValueError("a packet carries at most 14 payload bytes")
    b = bytearray(PACKET_LEN)
    b[0] = REPORT_ID
    b[1] = cmd
    b[2] = total
    b[3] = index
    b[4] = ((sub << 4) | len(chunk)) & 0xFF
    b[5:5 + len(chunk)] = chunk
    b[19] = checksum(b)
    return bytes(b)


def split_packets(cmd: int, sub: int, data: bytes) -> list[bytes]:
    chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [b""]
    return [build_packet(cmd, len(chunks), i, sub, c) for i, c in enumerate(chunks)]


def read_request(cmd: int, sub: int = 0) -> bytes:
    return build_packet(cmd | READ, 1, 0, sub, b"")


@dataclass
class Reply:
    cmd: int
    total: int
    index: int
    error: bool
    data: bytes


def parse_packet(r: bytes) -> Reply | None:
    """Decode a report from the keyboard; None if it isn't a valid config packet."""
    if len(r) < PACKET_LEN or r[0] != REPORT_ID or checksum(r) != r[19]:
        return None
    return Reply(cmd=r[1], total=r[2] & 0x7F, index=r[3],
                 error=bool(r[2] & 0x80), data=bytes(r[5:5 + (r[4] & 0x0F)]))


# ----------------------------------------------------------------- effects
@dataclass(frozen=True)
class Effect:
    hw: int
    name: str
    speed: bool
    color: bool


# Firmware effect numbers as observed on a real F75 (every number 1-34 was tried).
# The official app's names/numbering (KB.ini LedOpt) don't match the firmware.
# 9, 14, 18-31, 33, 34 show nothing; 21 and 29 show the per-key table only after
# it is re-sent.
EFFECTS = [
    Effect(1, "static", False, True),
    Effect(2, "breathing", True, True),
    Effect(3, "spectrum", True, False),     # multicolor breathing
    Effect(4, "ripple-row", True, True),    # reactive: spreads along the pressed key's row
    Effect(5, "raindrops", True, True),
    Effect(6, "wave", True, True),          # slow left-to-right
    Effect(7, "ripple", True, True),        # reactive: spreads over the whole board
    Effect(8, "twinkle", True, True),       # random keys light up
    Effect(10, "snake", True, True),
    Effect(11, "stream", True, True),       # left-to-right animation
    Effect(12, "reactive", True, True),     # pressed key lights up
    Effect(13, "center-wave", True, True),  # slides from the middle to both sides
    Effect(15, "rainbow-wheel", True, False),
    Effect(16, "waterfall", True, False),
    Effect(17, "center-flash", True, True), # fast flicker from the middle outwards
    Effect(32, "custom", False, False),     # per-key RGB table (command 0x02), updates live
]
EFFECT_BY_NAME = {e.name: e for e in EFFECTS}
EFFECT_BY_HW = {e.hw: e for e in EFFECTS}

COLORS = ["red", "green", "blue", "yellow", "purple", "cyan", "white", "multi"]

# Side light modes, verified on hardware. Bytes 19-21 (color, brightness, speed in the
# official app) showed no visible effect on the F75.
SIDE_MODES = ["off", "fill", "breathing", "static"]  # fill: LEDs light up top to bottom

# Knob modes, verified on hardware:
#   media    (Shift/Win blink blue on toggle):  turn = volume, press = mute
#   lighting (Shift/Win blink green on toggle): turn = brightness, press = next effect
KNOB_MODES = ["media", "lighting"]

OS_MODES = ["windows", "android", "mac"]  # verified on hardware (Fn+W, Fn+Q, Fn+E)

# Sleep timer: the official app (KB.ini SleepUI / SleepHW) offers these and stores
# seconds / 30. Factory value 2 = 1 minute, verified with a stopwatch; 0 = never
# (the lights stayed on overnight).
SLEEP_UNIT = 30
SLEEP_CHOICES = [60, 90, 120, 180, 240, 300, 600, 900, 1200]
SLEEP_MAX = 1200


def sleep_text(seconds: int) -> str:
    if seconds == 0:
        return "never"
    return f"{seconds // 60} min" if seconds % 60 == 0 else f"{seconds / 60:g} min"


@dataclass
class EffectSlot:
    brightness: int  # 0-9
    speed: int       # 0-4
    color: int       # 0-6 palette color, 7 = multicolor


class LedConfig:
    """The 128-byte lighting block read with 0x44."""

    def __init__(self, raw: bytes):
        if len(raw) != LED_LEN or raw[-2:] != LED_MAGIC:
            raise ValueError("unexpected LED config block")
        self.raw = bytearray(raw)

    @property
    def effect(self) -> int:
        return self.raw[LED_EFFECT_OFFSET]

    @effect.setter
    def effect(self, hw: int) -> None:
        self.raw[LED_EFFECT_OFFSET] = hw

    @property
    def side_mode(self) -> int:
        return self.raw[LED_SIDE_MODE_OFFSET]

    @side_mode.setter
    def side_mode(self, mode: int) -> None:
        if not 0 <= mode < len(SIDE_MODES):
            raise ValueError(f"side light mode must be 0-{len(SIDE_MODES) - 1}")
        self.raw[LED_SIDE_MODE_OFFSET] = mode

    @property
    def win_lock(self) -> bool:
        return bool(self.raw[LED_WIN_LOCK_OFFSET])

    @win_lock.setter
    def win_lock(self, locked: bool) -> None:
        self.raw[LED_WIN_LOCK_OFFSET] = int(locked)

    @property
    def os_mode(self) -> int:
        return self.raw[LED_OS_MODE_OFFSET]

    @os_mode.setter
    def os_mode(self, mode: int) -> None:
        if not 0 <= mode < len(OS_MODES):
            raise ValueError(f"OS mode must be 0-{len(OS_MODES) - 1}")
        self.raw[LED_OS_MODE_OFFSET] = mode

    @property
    def knob_mode(self) -> int:
        return self.raw[LED_KNOB_MODE_OFFSET]

    @knob_mode.setter
    def knob_mode(self, mode: int) -> None:
        if not 0 <= mode < len(KNOB_MODES):
            raise ValueError(f"knob mode must be 0-{len(KNOB_MODES) - 1}")
        self.raw[LED_KNOB_MODE_OFFSET] = mode

    @property
    def sleep(self) -> int:
        """Seconds of idle time before the keyboard sleeps (wireless only); 0 = never."""
        return self.raw[LED_SLEEP_OFFSET] * SLEEP_UNIT

    @sleep.setter
    def sleep(self, seconds: int) -> None:
        if seconds % SLEEP_UNIT or not 0 <= seconds <= SLEEP_MAX:
            raise ValueError(f"sleep time must be a multiple of {SLEEP_UNIT} s, "
                             f"at most {SLEEP_MAX // 60} min (0 = never)")
        self.raw[LED_SLEEP_OFFSET] = seconds // SLEEP_UNIT

    def _off(self, hw: int) -> int:
        if not 1 <= hw <= LED_SLOTS:
            raise ValueError(f"effect {hw} has no settings slot")
        return LED_SLOTS_OFFSET + 2 * (hw - 1)

    def slot(self, hw: int) -> EffectSlot:
        o = self._off(hw)
        return EffectSlot(self.raw[o], self.raw[o + 1] >> 4, self.raw[o + 1] & 0x0F)

    def set_slot(self, hw: int, s: EffectSlot) -> None:
        if not (0 <= s.brightness <= 9 and 0 <= s.speed <= 4 and 0 <= s.color <= 7):
            raise ValueError("brightness must be 0-9, speed 0-4, color 0-7")
        o = self._off(hw)
        self.raw[o] = s.brightness
        self.raw[o + 1] = (s.speed << 4) | s.color

    def to_bytes(self) -> bytes:
        return bytes(self.raw)


# ---------------------------------------------------------- per-key colors
def custom_from_colors(colors: dict[int, tuple[int, int, int]]) -> bytes:
    """{index: (r, g, b)} -> 378 bytes (all R, then all G, then all B)."""
    b = bytearray(CUSTOM_LEN)
    for i, (r, g, bl) in colors.items():
        b[i], b[MATRIX_LEN + i], b[2 * MATRIX_LEN + i] = r, g, bl
    return bytes(b)


def median_cut(groups: dict[tuple[int, int, int], list[int]], n: int) -> dict[tuple[int, int, int], list[int]]:
    """Merge {color: keys} into at most n groups, each shown in the average color.

    The group with the widest spread in one channel is split at its median, until
    there are n. Similar colors end up together, so nothing changes hue.
    """
    if len(groups) <= n:
        return dict(groups)
    boxes = [list(groups.items())]

    def spread(box):
        return max((max(c[ch] for c, _ in box) - min(c[ch] for c, _ in box), ch) for ch in range(3))

    while len(boxes) < n:
        box = max(boxes, key=lambda b: spread(b)[0])
        width, ch = spread(box)
        if width == 0:
            break
        box.sort(key=lambda item: item[0][ch])
        half = len(box) // 2
        boxes.remove(box)
        boxes += [box[:half], box[half:]]
    merged: dict[tuple[int, int, int], list[int]] = {}
    for box in boxes:
        keys = [i for _, ks in box for i in ks]
        avg = tuple(round(sum(c[ch] * len(ks) for c, ks in box) / len(keys)) for ch in range(3))
        merged.setdefault(avg, []).extend(keys)
    return merged


def live_frame(groups: dict[tuple[int, int, int], list[int]]) -> bytes:
    """{color: [index…]} -> a real-time frame for CMD_LIVE / LIVE_KEYS.

    The frame is a list of groups [R, G, B, count, index…]. Keys that aren't
    listed go dark, so black groups are left out.
    """
    out = bytearray()
    for (r, g, b), keys in groups.items():
        if keys and (r or g or b):
            out += bytes([r, g, b, len(keys), *sorted(keys)])
    if not out:
        return bytes([0, 0, 0, 1, 0])  # a single dark key: everything off
    if len(out) > LIVE_MAX:
        raise ValueError(f"real-time frame too long ({len(out)} bytes, at most {LIVE_MAX})")
    return bytes(out)


def colors_from_live(frame: bytes) -> dict[int, tuple[int, int, int]]:
    """The key colors a real-time frame shows (unlisted keys are dark)."""
    colors = {}
    i = 0
    while i + 4 <= len(frame):
        n = frame[i + 3]
        for idx in frame[i + 4:i + 4 + n]:
            colors[idx] = tuple(frame[i:i + 3])
        i += 4 + n
    return colors


def colors_from_custom(raw: bytes) -> dict[int, tuple[int, int, int]]:
    n = MATRIX_LEN
    return {i: (raw[i], raw[n + i], raw[2 * n + i]) for i in range(n)}


def parse_rgb(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"color must be 6 hex digits (e.g. ff0000): {s!r}")
    v = int(s, 16)
    return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF


# ---------------------------------------------------------------- palettes
# Command 0x09 / 0x49: one palette per effect number 0-22, each holding the 7 colors
# (RGB) that an effect's color setting 0-6 picks from, then 7 bytes of unknown
# meaning that are kept as read. Verified on hardware: palette n belongs to effect n
# (static 1, breathing 2, center-wave 13) and a write shows at once.
PALETTE_LEN = 490
PALETTE_COUNT = 23
PALETTE_COLORS = 7
DEFAULT_PALETTE = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
                   (255, 0, 255), (0, 255, 255), (255, 255, 255)]  # factory, for every effect


def _palette_offset(hw: int, color: int) -> int:
    if not 0 <= hw < PALETTE_COUNT:
        raise ValueError(f"effect {hw} has no palette")
    if not 0 <= color < PALETTE_COLORS:
        raise ValueError(f"color must be 0-{PALETTE_COLORS - 1} ({', '.join(COLORS[:PALETTE_COLORS])})")
    return hw * PALETTE_COLORS * 3 + color * 3


def palette_color(raw: bytes, hw: int, color: int) -> tuple[int, int, int]:
    o = _palette_offset(hw, color)
    return raw[o], raw[o + 1], raw[o + 2]


def set_palette_color(raw: bytes, hw: int, color: int, rgb: tuple[int, int, int]) -> bytes:
    o = _palette_offset(hw, color)
    b = bytearray(raw)
    b[o:o + 3] = bytes(rgb)
    return bytes(b)


def reset_palette(raw: bytes, hw: int) -> bytes:
    for color, rgb in enumerate(DEFAULT_PALETTE):
        raw = set_palette_color(raw, hw, color, rgb)
    return raw


def rgb_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


# ------------------------------------------------------------------ keymap
def matrix_entry(raw: bytes, index: int) -> bytes:
    return raw[4 * index:4 * index + 4]


def set_matrix_entry(raw: bytes, index: int, entry: bytes) -> bytes:
    if len(entry) != 4:
        raise ValueError("a keymap entry is 4 bytes")
    b = bytearray(raw)
    b[4 * index:4 * index + 4] = entry
    return bytes(b)


def key_entry(hid: int = 0, modifiers: int = 0) -> bytes:
    """Plain key entry: [0, modifier bits, 0, HID usage]."""
    return bytes([0x00, modifiers & 0xFF, 0x00, hid & 0xFF])
