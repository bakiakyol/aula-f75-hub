"""aula - Linux configuration tool for the AULA F75 (command line)."""

import argparse
import os
import sys

from . import keymap as K
from . import macros as M
from . import presets as T
from . import protocol as P
from .device import AulaError, Keyboard, find_devices


def _effect(arg: str) -> P.Effect:
    if arg.isdigit() and int(arg) in P.EFFECT_BY_HW:
        return P.EFFECT_BY_HW[int(arg)]
    if arg.isdigit() and 1 <= int(arg) <= P.LED_SLOTS:  # unnamed firmware effect, for exploring
        return P.Effect(int(arg), f"hw{arg}", True, True)
    if arg in P.EFFECT_BY_NAME:
        return P.EFFECT_BY_NAME[arg]
    raise AulaError(f"unknown effect: {arg!r} (see 'aula effects')")


def _color(arg: str) -> int:
    if arg.isdigit() and 0 <= int(arg) <= 7:
        return int(arg)
    if arg in P.COLORS:
        return P.COLORS.index(arg)
    raise AulaError(f"unknown color: {arg!r} (choices: {', '.join(P.COLORS)})")


def cmd_info(kb: Keyboard, a) -> None:
    led = kb.get_led()
    e = P.EFFECT_BY_HW.get(led.effect)
    print(f"Device    : {kb.path} ({kb.mode})")
    print(f"Effect    : {led.effect} ({e.name if e else 'unknown'})")
    if 1 <= led.effect <= P.LED_SLOTS:
        s = led.slot(led.effect)
        print(f"Brightness: {s.brightness}/9   Speed: {s.speed}/4   Color: {P.COLORS[s.color]}")
    battery = kb.get_battery()
    print(f"Battery   : {battery}% (experimental)" if battery is not None else "Battery   : ?")
    side = led.side_mode
    print(f"Side light: {P.SIDE_MODES[side] if side < len(P.SIDE_MODES) else side}")
    knob = led.knob_mode
    print(f"Knob      : {P.KNOB_MODES[knob] if knob < len(P.KNOB_MODES) else knob}")
    os_mode = led.os_mode
    print(f"OS mode   : {P.OS_MODES[os_mode] if os_mode < len(P.OS_MODES) else os_mode}")
    print(f"Win lock  : {'on' if led.win_lock else 'off'}")


def cmd_effects(_kb, a) -> None:
    for e in P.EFFECTS:
        opts = [o for o, ok in (("speed", e.speed), ("color", e.color)) if ok]
        print(f"{e.hw:3}  {e.name:14} {', '.join(opts)}")
    print("\nColors:", ", ".join(f"{i}={c}" for i, c in enumerate(P.COLORS)))


def cmd_effect(kb: Keyboard, a) -> None:
    e = _effect(a.effect)
    led = kb.get_led()
    led.effect = e.hw
    if 1 <= e.hw <= P.LED_SLOTS:
        s = led.slot(e.hw)
        if a.brightness is not None:
            s.brightness = a.brightness
        if a.speed is not None:
            s.speed = a.speed
        if a.color is not None:
            s.color = _color(a.color)
        led.set_slot(e.hw, s)
    kb.set_led(led)
    print(f"Effect: {e.name}")


def cmd_brightness(kb: Keyboard, a) -> None:
    led = kb.get_led()
    s = led.slot(led.effect)
    s.brightness = a.value
    led.set_slot(led.effect, s)
    kb.set_led(led)
    print(f"Brightness: {a.value}/9")


def cmd_side_light(kb: Keyboard, a) -> None:
    led = kb.get_led()
    led.side_mode = P.SIDE_MODES.index(a.mode)
    kb.set_led(led)
    print(f"Side light: {a.mode}")


def cmd_knob(kb: Keyboard, a) -> None:
    led = kb.get_led()
    led.knob_mode = P.KNOB_MODES.index(a.mode)
    kb.set_led(led)
    print(f"Knob: {a.mode}")


def cmd_os(kb: Keyboard, a) -> None:
    led = kb.get_led()
    led.os_mode = P.OS_MODES.index(a.mode)
    kb.set_led(led)
    print(f"OS mode: {a.mode}")


def cmd_win_lock(kb: Keyboard, a) -> None:
    led = kb.get_led()
    led.win_lock = a.state == "on"
    kb.set_led(led)
    print(f"Win lock: {a.state}")


def cmd_keys(_kb, a) -> None:
    for idx, name, label, _ in sorted(K.KEYS, key=lambda k: k[0]):
        print(f"#{idx:<4} {name:10} {label}")
    print("\nTurkish Q aliases:", ", ".join(f"{k}→{v}" for k, v in K.TR_ALIASES.items()))


def cmd_key_color(kb: Keyboard, a) -> None:
    colors = {} if a.clear else P.colors_from_custom(kb.get_custom())
    for item in a.assignments:
        name, sep, value = item.partition("=")
        if not sep:
            raise AulaError(f"cannot parse {item!r}, expected e.g. esc=ff0000")
        rgb = P.parse_rgb(value)
        if name.lower() == "all":
            for idx, *_ in K.KEYS:
                colors[idx] = rgb
        else:
            colors[K.key_index(name)] = rgb
    led = kb.get_led()
    custom = P.EFFECT_BY_NAME["custom"].hw
    if led.effect != custom:
        led.effect = custom
        kb.set_led(led)
    kb.set_custom(P.custom_from_colors(colors))
    print(f"Sent {len(a.assignments)} color assignment(s) (effect: custom)")


def cmd_preset(kb: Keyboard, a) -> None:
    if a.name is None:
        for p in T.PRESETS:
            print(f"{p.name:12} {p.description}")
        return
    if a.name not in T.PRESET_BY_NAME:
        raise AulaError(f"unknown preset: {a.name!r} (run 'aula preset' to list them)")
    led = kb.get_led()
    custom = P.EFFECT_BY_NAME["custom"].hw
    if led.effect != custom:
        led.effect = custom
        kb.set_led(led)
    kb.set_custom(P.custom_from_colors(T.render(T.PRESET_BY_NAME[a.name])))
    print(f"Preset: {a.name}")


def cmd_remap(kb: Keyboard, a) -> None:
    idx = K.key_index(a.key)
    target = a.target.lower()
    target = K.TR_ALIASES.get(target, target)
    if target in K.MODIFIERS:
        entry = P.key_entry(modifiers=K.MODIFIERS[target])
    elif target in K.HID:
        entry = P.key_entry(hid=K.HID[target])
    elif target == "none":
        entry = P.key_entry()
    else:
        raise AulaError(f"unknown target: {a.target!r}")
    raw = kb.get_matrix(a.layer)
    old = P.matrix_entry(raw, idx)
    kb.set_matrix(P.set_matrix_entry(raw, idx, entry), a.layer)
    check = P.matrix_entry(kb.get_matrix(a.layer), idx)
    if check != entry:
        raise AulaError(f"verification failed: expected {entry.hex()}, read back {check.hex()}")
    print(f"{a.key} (layer {a.layer}): {old.hex()} -> {entry.hex()}")


# ------------------------------------------------------------------ macros
def _macro_mode(a) -> tuple[int, int]:
    if a.while_held:
        return M.REPEAT_HOLD, 1
    if a.until_key:
        return M.REPEAT_UNTIL_KEY, 1
    return M.REPEAT_TIMES, a.repeat


def _factory_entry(index: int, layer: int) -> bytes:
    fname = "cmd_41.hex" if layer == 0 else f"cmd_41_layer{layer}.hex"
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup", fname)
    if os.path.exists(path):
        with open(path) as f:
            return P.matrix_entry(bytes.fromhex(f.read().strip()), index)
    return P.key_entry()


def _assign_macro(kb: Keyboard, key: str, layer: int, entry: bytes) -> None:
    idx = K.key_index(key)
    raw = kb.get_matrix(layer)
    kb.set_matrix(P.set_matrix_entry(raw, idx, entry), layer)
    if P.matrix_entry(kb.get_matrix(layer), idx) != entry:
        raise AulaError("verification failed after assigning the macro")


def delete_macro(kb: Keyboard, macros: list, index: int) -> list:
    """Remove macro `index` from the store and fix the keymap: keys pointing at later
    macros move down by one, keys of the deleted one get their factory function back."""
    macros = [m for i, m in enumerate(macros) if i != index]
    kb.set_macro_store(M.build_store(macros))
    for layer in range(4):
        raw = kb.get_matrix(layer)
        new = bytearray(raw)
        for idx in range(K.MATRIX_LEN):
            e = P.matrix_entry(raw, idx)
            if e[0] != M.MACRO_ENTRY:
                continue
            if e[3] == index:
                new[4 * idx:4 * idx + 4] = _factory_entry(idx, layer)
            elif e[3] > index:
                new[4 * idx + 3] = e[3] - 1
        if bytes(new) != raw:
            kb.set_matrix(bytes(new), layer)
    return macros


def cmd_macro_list(kb: Keyboard, a) -> None:
    macros = M.parse_store(kb.get_macro_store())
    if not macros:
        print("No macros stored.")
        return
    users: dict[int, list[str]] = {}
    for layer in range(2):
        raw = kb.get_matrix(layer)
        for idx, name, *_ in K.KEYS:
            e = P.matrix_entry(raw, idx)
            if e[0] == M.MACRO_ENTRY:
                mode = {1: f"×{e[2]}", 2: "while held", 4: "until a key"}.get(e[1], f"mode {e[1]}")
                users.setdefault(e[3], []).append(f"{'Fn+' if layer else ''}{name} ({mode})")
    for i, m in enumerate(macros):
        keys = ", ".join(users.get(i, [])) or "not assigned"
        print(f"{i}: {m.name}  [{keys}]")
        print("   " + " ".join(e.describe() for e in m.events))


def cmd_macro_set(kb: Keyboard, a) -> None:
    layout = a.layout or M.detect_layout()
    events = M.parse_steps(a.steps, a.delay, layout)
    macros = M.parse_store(kb.get_macro_store())
    index = next((i for i, m in enumerate(macros) if m.name == a.name), None)
    if index is None:
        macros.append(M.Macro(a.name, events))
        index = len(macros) - 1
    else:
        macros[index] = M.Macro(a.name, events)
    kb.set_macro_store(M.build_store(macros))
    typed = f", text for the {M.LAYOUTS[layout]} layout" if any(x.startswith("text:") for x in a.steps) else ""
    print(f"Macro {index}: {a.name} ({len(events)} events{typed})")
    if a.key:
        mode, count = _macro_mode(a)
        _assign_macro(kb, a.key, a.layer, M.macro_entry(index, mode, count))
        print(f"Assigned to {'Fn+' if a.layer else ''}{a.key}")


def cmd_macro_assign(kb: Keyboard, a) -> None:
    macros = M.parse_store(kb.get_macro_store())
    index = next((i for i, m in enumerate(macros) if m.name == a.name), None)
    if index is None:
        raise AulaError(f"no macro named {a.name!r} (see 'aula macro list')")
    mode, count = _macro_mode(a)
    _assign_macro(kb, a.key, a.layer, M.macro_entry(index, mode, count))
    print(f"{a.name} assigned to {'Fn+' if a.layer else ''}{a.key}")


def cmd_macro_delete(kb: Keyboard, a) -> None:
    macros = M.parse_store(kb.get_macro_store())
    index = next((i for i, m in enumerate(macros) if m.name == a.name), None)
    if index is None:
        raise AulaError(f"no macro named {a.name!r} (see 'aula macro list')")
    delete_macro(kb, macros, index)
    print(f"Deleted macro {a.name!r}")


BACKUP = [  # (file, read function, write function)
    ("cmd_41.hex", lambda kb: kb.get_matrix(0), lambda kb, d: kb.set_matrix(d, 0)),
    ("cmd_41_layer1.hex", lambda kb: kb.get_matrix(1), lambda kb, d: kb.set_matrix(d, 1)),
    ("cmd_41_layer2.hex", lambda kb: kb.get_matrix(2), lambda kb, d: kb.set_matrix(d, 2)),
    ("cmd_41_layer3.hex", lambda kb: kb.get_matrix(3), lambda kb, d: kb.set_matrix(d, 3)),
    ("cmd_44.hex", lambda kb: kb.get_led().to_bytes(), lambda kb, d: kb.set_led(P.LedConfig(d))),
    # the custom color table has to be sent after the LED block
    ("cmd_42.hex", lambda kb: kb.get_custom(), lambda kb, d: kb.set_custom(d)),
]


def cmd_backup(kb: Keyboard, a) -> None:
    os.makedirs(a.folder, exist_ok=True)
    for fname, get, _ in BACKUP:
        with open(os.path.join(a.folder, fname), "w") as f:
            f.write(get(kb).hex())
        print("saved:", fname)


def cmd_restore(kb: Keyboard, a) -> None:
    for fname, _, put in BACKUP:
        path = os.path.join(a.folder, fname)
        if not os.path.exists(path):
            print("skipped (missing):", fname)
            continue
        with open(path) as f:
            put(kb, bytes.fromhex(f.read().strip()))
        print("restored:", fname)


def cmd_raw_read(kb: Keyboard, a) -> None:
    data = kb.read(int(a.command, 16) & 0x3F, a.sub)
    print(f"{len(data)} bytes:", data.hex(" "))


def cmd_gui(_kb, a) -> None:
    from .gui import main as gui_main  # GTK is only needed for the GUI
    gui_main()


def cmd_devices(_kb, a) -> None:
    devs = find_devices()
    if not devs:
        print("No AULA F75 found.")
    for d in devs:
        status = "supported" if d["supported"] else "not supported yet"
        print(f"{d['path']:14} {d['mode']:12} {d['name']}  ({status})")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="aula", description="AULA F75 configuration tool for Linux")
    p.add_argument("--device", help="hidraw path (e.g. /dev/hidraw2); auto-detected if omitted")
    sp = p.add_subparsers(dest="command", required=True)

    sp.add_parser("gui", help="open the graphical interface").set_defaults(f=cmd_gui, no_kb=True)
    sp.add_parser("devices", help="list connected keyboards").set_defaults(f=cmd_devices, no_kb=True)
    sp.add_parser("info", help="show current lighting settings").set_defaults(f=cmd_info)
    sp.add_parser("effects", help="list effects and colors").set_defaults(f=cmd_effects, no_kb=True)
    sp.add_parser("keys", help="list key names").set_defaults(f=cmd_keys, no_kb=True)

    s = sp.add_parser("effect", help="change the lighting effect")
    s.add_argument("effect", help="effect name or number")
    s.add_argument("-c", "--color", help="color name or 0-7")
    s.add_argument("-b", "--brightness", type=int, choices=range(10), metavar="0-9")
    s.add_argument("-s", "--speed", type=int, choices=range(5), metavar="0-4")
    s.set_defaults(f=cmd_effect)

    s = sp.add_parser("brightness", help="brightness of the current effect")
    s.add_argument("value", type=int, choices=range(10), metavar="0-9")
    s.set_defaults(f=cmd_brightness)

    s = sp.add_parser("side-light", help="white bar next to Esc")
    s.add_argument("mode", choices=P.SIDE_MODES)
    s.set_defaults(f=cmd_side_light)

    s = sp.add_parser("knob", help="knob function: media (volume) or lighting (brightness/effect)")
    s.add_argument("mode", choices=P.KNOB_MODES)
    s.set_defaults(f=cmd_knob)

    s = sp.add_parser("os", help="OS mode (same as Fn+W / Fn+Q / Fn+E)")
    s.add_argument("mode", choices=P.OS_MODES)
    s.set_defaults(f=cmd_os)

    s = sp.add_parser("win-lock", help="disable/enable the Windows key (same as Fn+Win)")
    s.add_argument("state", choices=["on", "off"])
    s.set_defaults(f=cmd_win_lock)

    s = sp.add_parser("key-color", help="set individual key colors (custom effect)")
    s.add_argument("assignments", nargs="+", metavar="KEY=RGB", help="e.g. esc=ff0000 w=00ff00 all=000000")
    s.add_argument("--clear", action="store_true", help="turn all other keys off first")
    s.set_defaults(f=cmd_key_color)

    s = sp.add_parser("preset", help="load a built-in per-key color theme (no name: list them)")
    s.add_argument("name", nargs="?")
    s.set_defaults(f=cmd_preset)

    s = sp.add_parser("remap", help="remap a key")
    s.add_argument("key", help="physical key to change, e.g. capslock")
    s.add_argument("target", help="new function, e.g. lctrl, esc, f5, none")
    s.add_argument("-l", "--layer", type=int, default=0, choices=range(4))
    s.set_defaults(f=cmd_remap)

    mp = sp.add_parser("macro", help="keyboard macros").add_subparsers(dest="macro_cmd", required=True)
    mp.add_parser("list", help="show stored macros and their keys").set_defaults(f=cmd_macro_list)

    def repeat_opts(q):
        g = q.add_mutually_exclusive_group()
        g.add_argument("--repeat", type=int, default=1, metavar="N", help="run N times (default 1)")
        g.add_argument("--while-held", action="store_true", help="repeat while the key is held")
        g.add_argument("--until-key", action="store_true", help="repeat until any key is pressed")
        q.add_argument("-l", "--layer", type=int, default=0, choices=range(4))

    s = mp.add_parser("set", help="create or replace a macro",
                      description="Steps: key combos (ctrl+c, enter, f5), 'wait:MS', 'text:hello'.")
    s.add_argument("name")
    s.add_argument("steps", nargs="+")
    s.add_argument("--key", help="also assign it to this key")
    s.add_argument("--delay", type=int, default=20, help="ms between events (default 20)")
    s.add_argument("--layout", choices=list(M.LAYOUTS),
                   help="keyboard layout of the computer, for text steps (default: detected)")
    repeat_opts(s)
    s.set_defaults(f=cmd_macro_set)

    s = mp.add_parser("assign", help="assign a stored macro to a key")
    s.add_argument("key")
    s.add_argument("name")
    repeat_opts(s)
    s.set_defaults(f=cmd_macro_assign)

    s = mp.add_parser("delete", help="delete a macro (its keys get their factory function back)")
    s.add_argument("name")
    s.set_defaults(f=cmd_macro_delete)

    s = sp.add_parser("backup", help="save keyboard settings to a folder")
    s.add_argument("folder")
    s.set_defaults(f=cmd_backup)

    s = sp.add_parser("restore", help="restore keyboard settings from a folder")
    s.add_argument("folder")
    s.set_defaults(f=cmd_restore)

    s = sp.add_parser("raw-read", help="(developer) raw read command")
    s.add_argument("command", help="hex, e.g. 44")
    s.add_argument("sub", type=int, nargs="?", default=0)
    s.set_defaults(f=cmd_raw_read)

    a = p.parse_args(argv)
    try:
        if getattr(a, "no_kb", False) or (a.command == "preset" and a.name is None):
            a.f(None, a)
        else:
            with Keyboard(a.device) as kb:
                a.f(kb, a)
    except (AulaError, KeyError, ValueError) as e:
        print("Error:", e.args[0] if e.args else e, file=sys.stderr)
        return 1
    return 0
