"""AULA F75 key layout.

Every key has a "matrix index" (0-125). The same index addresses the key in
the keymap table (command 0x01/0x41, 4 bytes per key) and in the per-key RGB
table (command 0x02/0x42).

Positions come from the official app's KB.ini (x1, y1, x2, y2 in pixels).
Note: KB.ini labels 53 as "FN" and 59 as "RCtrl", but the keyboard's own
matrix holds RAlt at 53 and Fn at 59; the real assignment is used here.
"""

MATRIX_LEN = 126

# (index, short name, label, (x1, y1, x2, y2))
KEYS = [
    (0, "esc", "Esc", (30, 30, 55, 57)),
    (12, "f1", "F1", (107, 30, 132, 57)),
    (18, "f2", "F2", (144, 30, 169, 57)),
    (24, "f3", "F3", (183, 30, 208, 57)),
    (30, "f4", "F4", (222, 30, 247, 57)),
    (36, "f5", "F5", (269, 30, 294, 57)),
    (42, "f6", "F6", (305, 30, 330, 57)),
    (48, "f7", "F7", (343, 30, 368, 57)),
    (54, "f8", "F8", (388, 30, 413, 57)),
    (60, "f9", "F9", (439, 30, 464, 57)),
    (66, "f10", "F10", (477, 30, 502, 57)),
    (72, "f11", "F11", (516, 30, 541, 57)),
    (78, "f12", "F12", (555, 30, 580, 57)),
    (1, "grave", "`", (31, 81, 56, 108)),
    (7, "1", "1", (70, 81, 95, 108)),
    (13, "2", "2", (108, 81, 133, 108)),
    (19, "3", "3", (147, 81, 172, 108)),
    (25, "4", "4", (184, 81, 209, 108)),
    (31, "5", "5", (223, 81, 248, 108)),
    (37, "6", "6", (262, 81, 287, 108)),
    (43, "7", "7", (300, 81, 325, 108)),
    (49, "8", "8", (338, 81, 363, 108)),
    (55, "9", "9", (377, 81, 402, 108)),
    (61, "0", "0", (416, 81, 441, 108)),
    (67, "minus", "-", (453, 81, 478, 108)),
    (73, "equal", "=", (491, 81, 516, 108)),
    (79, "backspace", "Backspace", (531, 81, 591, 108)),
    (85, "delete", "Del", (604, 81, 629, 108)),
    (2, "tab", "Tab", (34, 120, 78, 147)),
    (8, "q", "Q", (89, 119, 114, 146)),
    (14, "w", "W", (127, 119, 152, 146)),
    (20, "e", "E", (165, 119, 190, 146)),
    (26, "r", "R", (204, 119, 229, 146)),
    (32, "t", "T", (242, 119, 267, 146)),
    (38, "y", "Y", (280, 119, 305, 146)),
    (44, "u", "U", (318, 119, 343, 146)),
    (50, "i", "I", (356, 119, 381, 146)),
    (56, "o", "O", (395, 119, 420, 146)),
    (62, "p", "P", (433, 119, 458, 146)),
    (68, "lbracket", "[", (471, 119, 496, 146)),
    (74, "rbracket", "]", (509, 119, 534, 146)),
    (80, "backslash", "\\", (549, 119, 593, 146)),
    (86, "pgup", "PgUp", (605, 120, 630, 147)),
    (3, "capslock", "Caps", (33, 158, 85, 185)),
    (9, "a", "A", (98, 158, 123, 185)),
    (15, "s", "S", (136, 158, 161, 185)),
    (21, "d", "D", (174, 158, 199, 185)),
    (27, "f", "F", (213, 158, 238, 185)),
    (33, "g", "G", (252, 158, 277, 185)),
    (39, "h", "H", (290, 158, 315, 185)),
    (45, "j", "J", (327, 158, 352, 185)),
    (51, "k", "K", (366, 158, 391, 185)),
    (57, "l", "L", (405, 158, 430, 185)),
    (63, "semicolon", ";", (443, 158, 468, 185)),
    (69, "quote", "'", (481, 158, 506, 185)),
    (81, "enter", "Enter", (521, 158, 591, 185)),
    (87, "pgdn", "PgDn", (604, 159, 629, 186)),
    (4, "lshift", "Shift", (33, 195, 105, 222)),
    (10, "z", "Z", (116, 195, 141, 222)),
    (16, "x", "X", (155, 195, 180, 222)),
    (22, "c", "C", (193, 195, 218, 222)),
    (28, "v", "V", (232, 195, 257, 222)),
    (34, "b", "B", (270, 195, 295, 222)),
    (40, "n", "N", (309, 195, 334, 222)),
    (46, "m", "M", (347, 195, 372, 222)),
    (52, "comma", ",", (384, 195, 409, 222)),
    (58, "period", ".", (424, 195, 449, 222)),
    (64, "slash", "/", (463, 195, 488, 222)),
    (70, "rshift", "Shift", (502, 195, 558, 222)),
    (82, "up", "↑", (567, 195, 592, 222)),
    (88, "end", "End", (605, 195, 630, 222)),
    (5, "lctrl", "Ctrl", (34, 234, 69, 261)),
    (11, "lwin", "Win", (79, 234, 114, 261)),
    (17, "lalt", "Alt", (122, 234, 157, 261)),
    (35, "space", "Space", (174, 234, 400, 261)),
    (53, "ralt", "Alt", (414, 234, 449, 261)),
    (59, "fn", "Fn", (463, 234, 497, 261)),
    (77, "left", "←", (529, 234, 554, 261)),
    (83, "down", "↓", (568, 234, 593, 261)),
    (89, "right", "→", (605, 234, 630, 261)),
    (84, "knob", "Knob", (0, 0, 0, 0)),
]

BY_NAME = {name: idx for idx, name, _, _ in KEYS}
BY_INDEX = {idx: name for idx, name, _, _ in KEYS}

# Turkish Q layout: physical key under each Turkish letter
TR_ALIASES = {
    "ğ": "lbracket", "ü": "rbracket", "ş": "semicolon",
    "ö": "comma", "ç": "period", "ı": "i",
}

# USB HID usage codes (used as remap targets)
HID = {
    **{chr(ord("a") + i): 0x04 + i for i in range(26)},
    **{str(i): 0x1E + i - 1 for i in range(1, 10)}, "0": 0x27,
    "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    "minus": 0x2D, "equal": 0x2E, "lbracket": 0x2F, "rbracket": 0x30,
    "backslash": 0x31, "iso_hash": 0x32, "semicolon": 0x33, "quote": 0x34,
    "grave": 0x35, "comma": 0x36, "period": 0x37, "slash": 0x38, "capslock": 0x39,
    **{f"f{i}": 0x3A + i - 1 for i in range(1, 13)},
    "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48, "insert": 0x49,
    "home": 0x4A, "pgup": 0x4B, "delete": 0x4C, "end": 0x4D, "pgdn": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "iso_backslash": 0x64, "menu": 0x65,
}

# Linux input key codes (linux/input-event-codes.h) -> names in HID or MODIFIERS,
# for recording macros. X11/GTK hardware keycodes are these plus 8.
EVDEV = {
    1: "esc", **{2 + i: str((i + 1) % 10) for i in range(10)}, 12: "minus", 13: "equal",
    14: "backspace", 15: "tab", **{16 + i: c for i, c in enumerate("qwertyuiop")},
    26: "lbracket", 27: "rbracket", 28: "enter", 29: "lctrl",
    **{30 + i: c for i, c in enumerate("asdfghjkl")}, 39: "semicolon", 40: "quote",
    41: "grave", 42: "lshift", 43: "backslash", **{44 + i: c for i, c in enumerate("zxcvbnm")},
    51: "comma", 52: "period", 53: "slash", 54: "rshift", 56: "lalt", 57: "space",
    58: "capslock", **{59 + i: f"f{i + 1}" for i in range(10)}, 70: "scrolllock",
    86: "iso_backslash", 87: "f11", 88: "f12", 97: "rctrl", 99: "printscreen", 100: "ralt",
    102: "home", 103: "up", 104: "pgup", 105: "left", 106: "right", 107: "end",
    108: "down", 109: "pgdn", 110: "insert", 111: "delete", 119: "pause",
    125: "lwin", 126: "rwin", 127: "menu",
}

# Modifier keys: stored as bits in the second byte of a keymap entry
MODIFIERS = {
    "lctrl": 0x01, "lshift": 0x02, "lalt": 0x04, "lwin": 0x08,
    "rctrl": 0x10, "rshift": 0x20, "ralt": 0x40, "rwin": 0x80,
}


def key_index(name: str) -> int:
    """Resolve a key name to its matrix index. Use '#53' for a raw index."""
    n = name.strip().lower()
    n = TR_ALIASES.get(n, n)
    if n in BY_NAME:
        return BY_NAME[n]
    if n.startswith("#") and n[1:].isdigit() and int(n[1:]) < MATRIX_LEN:
        return int(n[1:])
    raise KeyError(f"unknown key: {name!r} (see 'aula keys')")
