"""Packet tests: expected values were captured from real keyboard traffic."""

import os
import sys
import unittest

from aula import keymap as K
from aula import protocol as P

BACKUP = os.path.join(os.path.dirname(__file__), "..", "backup")


def _backup(name):
    with open(os.path.join(BACKUP, name)) as f:
        return bytes.fromhex(f.read().strip())


class PacketTests(unittest.TestCase):
    def test_read_request_matches_capture(self):
        self.assertEqual(P.read_request(P.CMD_SET_LED).hex(" "),
                         "13 44 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 58")
        self.assertEqual(P.read_request(P.CMD_PROFILE)[-1], 0x5E)

    def test_led_write_packets_match_capture(self):
        led = _backup("cmd_44.hex")
        pkts = P.split_packets(P.CMD_SET_LED, 0, led)
        self.assertEqual(len(pkts), 10)
        self.assertEqual(pkts[0][:5].hex(" "), "13 04 0a 00 0e")
        self.assertEqual(pkts[9][:7].hex(" "), "13 04 0a 09 02 5a a5")
        for p in pkts:
            self.assertEqual(P.checksum(p), p[19])

    def test_parse_reply(self):
        r = bytes.fromhex("13 44 0a 09 02 5a a5" + " 00" * 12 + " 6b")
        rep = P.parse_packet(r)
        self.assertEqual((rep.cmd, rep.total, rep.index, rep.data), (0x44, 10, 9, b"\x5a\xa5"))
        self.assertIsNone(P.parse_packet(r[:-1] + b"\x00"))  # bad checksum


class LedConfigTests(unittest.TestCase):
    def test_slot_roundtrip(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        s = led.slot(1)
        s.color = 0
        led.set_slot(1, s)
        self.assertEqual(led.slot(1).color, 0)
        self.assertEqual(led.to_bytes()[-2:], P.LED_MAGIC)

    def test_side_mode(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        self.assertEqual(P.SIDE_MODES[led.side_mode], "static")  # original setting
        led.side_mode = P.SIDE_MODES.index("off")
        self.assertEqual(led.to_bytes()[18], 0)
        with self.assertRaises(ValueError):
            led.side_mode = 4

    def test_knob_mode(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        self.assertEqual(P.KNOB_MODES[led.knob_mode], "media")  # original setting
        led.knob_mode = P.KNOB_MODES.index("lighting")
        self.assertEqual(led.to_bytes()[26], 1)

    def test_os_and_win_lock(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        self.assertEqual(P.OS_MODES[led.os_mode], "windows")  # original settings
        self.assertFalse(led.win_lock)
        led.os_mode = P.OS_MODES.index("mac")
        led.win_lock = True
        self.assertEqual((led.to_bytes()[27], led.to_bytes()[15]), (2, 1))

    def test_sleep(self):
        from aula.cli import parse_duration
        led = P.LedConfig(_backup("cmd_44.hex"))
        self.assertEqual(led.sleep, 60)  # factory: 2 x 30 s, timed on hardware
        led.sleep = 300
        self.assertEqual(led.to_bytes()[24], 10)  # what the official app writes for 5 min
        self.assertEqual(P.sleep_text(90), "1.5 min")
        self.assertEqual([parse_duration(t) for t in ("5", "5m", "90s", "1.5m", "off")], [300, 300, 90, 90, 0])
        for bad in (45, 1230):
            with self.assertRaises(ValueError):
                led.sleep = bad

    def test_bad_values(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        with self.assertRaises(ValueError):
            led.set_slot(1, P.EffectSlot(10, 0, 0))


class CustomTableTests(unittest.TestCase):
    def test_planar_layout_matches_live_test(self):
        # Live test: ESC lit red, A green, W blue
        raw = P.custom_from_colors({K.key_index("esc"): (255, 0, 0),
                                    K.key_index("a"): (0, 255, 0),
                                    K.key_index("w"): (0, 0, 255)})
        self.assertEqual(len(raw), 378)
        self.assertEqual(raw[0], 0xFF)
        self.assertEqual(raw[126 + 9], 0xFF)
        self.assertEqual(raw[252 + 14], 0xFF)
        self.assertEqual(sum(raw), 3 * 0xFF)


class KeyReportTests(unittest.TestCase):
    def test_dongle_reports(self):
        from aula.backends.linux import _keys_down
        self.assertTrue(_keys_down(bytes([0, 0, 0x28, 0, 0, 0, 0, 0])))     # Enter on boot iface
        self.assertFalse(_keys_down(bytes(8)))
        self.assertTrue(_keys_down(bytes([4, 0, 0, 0, 0, 0, 1] + [0] * 14)))  # NKRO bit set
        self.assertIsNone(_keys_down(bytes([0x13] + [0] * 19)))             # config reply

    def test_bluetooth_reports(self):
        from aula.backends.linux import _keys_down
        self.assertTrue(_keys_down(bytes([1, 0, 0, 0x28, 0, 0, 0, 0, 0]), True))
        self.assertFalse(_keys_down(bytes([1] + [0] * 8), True))
        self.assertTrue(_keys_down(bytes([2, 0, 0, 0, 0, 0, 1] + [0] * 14), True))
        self.assertIsNone(_keys_down(bytes([4, 1]), True))  # system control, not keys


class KeyPressTests(unittest.TestCase):
    def test_reports_to_usages(self):
        from aula.backends.base import keys_in_report
        self.assertEqual(keys_in_report(bytes([0x02, 0, 0x04, 0x28, 0, 0, 0, 0])), {0xE1, 0x04, 0x28})  # shift a enter
        self.assertEqual(keys_in_report(bytes([0, 0, 1, 0, 0, 0, 0, 0])), frozenset())  # ErrorRollOver: no key
        nkro = bytearray(21)
        nkro[0], nkro[1 + 0x28 // 8] = 4, 1 << (0x28 % 8)
        self.assertEqual(keys_in_report(bytes(nkro)), {0x28})
        self.assertEqual(keys_in_report(bytes([1, 0x01, 0, 0x2C, 0, 0, 0, 0, 0]), True), {0xE0, 0x2C})
        self.assertIsNone(keys_in_report(bytes([0x13] + [0] * 19)))

    def test_tracker(self):
        from aula.backends.base import KeyTracker
        tr = KeyTracker()
        tr.feed("boot", frozenset({0x04}))
        tr.feed("nkro", frozenset({0x04, 0x05}))       # same key on two reports counts once
        self.assertEqual(tr.take_presses(), [0x04, 0x05])
        self.assertEqual(tr.take_presses(), [])
        tr.feed("boot", frozenset())
        self.assertEqual(tr.take_presses(), [])        # 'a' still held on NKRO
        tr.feed("nkro", frozenset())
        tr.feed("nkro", frozenset({0x04}))
        self.assertEqual(tr.take_presses(), [0x04])     # pressed again

    def test_key_presses(self):
        from aula.backends.base import KeyGuard
        from aula.device import Keyboard

        class Guard(KeyGuard):
            def presses(self):
                return [0x04, 0xE0, 0x68]               # a, left ctrl, F13 (not on the F75)

        kb = Keyboard.__new__(Keyboard)                 # no device opened
        kb._guard = Guard()
        self.assertEqual(kb.key_presses(), [K.key_index("a"), K.key_index("lctrl")])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux backend")
    def test_linux_guard_reads_presses(self):
        """The guard's read loop, with sockets standing in for the hidraw nodes
        (one report per read, like hidraw)."""
        import socket
        import time

        from aula.backends.base import KeyTracker
        from aula.backends.linux import LinuxKeyGuard
        boot_out, boot_in = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        nkro_out, nkro_in = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        guard = LinuxKeyGuard.__new__(LinuxKeyGuard)            # no device opened
        guard.bluetooth, guard._tracker, guard._last_key_event = False, KeyTracker(), time.monotonic()
        guard._key_fds = [boot_in.fileno(), nkro_in.fileno()]
        for sock in (boot_in, nkro_in):
            sock.setblocking(False)
        nkro = bytearray(21)
        nkro[0], nkro[1 + 0x28 // 8] = 4, 1 << (0x28 % 8)
        boot_out.send(bytes([0x02, 0, 0x04, 0, 0, 0, 0, 0]))     # shift + a
        nkro_out.send(bytes(nkro))                                 # enter, on the NKRO report
        boot_out.send(bytes(8))                                    # all up
        boot_out.send(bytes([0, 0, 1, 0, 0, 0, 0, 0]))             # ErrorRollOver: no new key
        time.sleep(0.05)
        self.assertEqual(guard.presses(), [0x04, 0xE1, 0x28])
        self.assertEqual(guard.presses(), [])
        for sock in (boot_out, boot_in, nkro_out, nkro_in):
            sock.close()

    def test_every_key_but_fn_has_a_usage(self):
        lit = {idx for idx, _n, _l, r in K.KEYS if r != (0, 0, 0, 0)}
        self.assertEqual(lit - set(K.USAGE_INDEX.values()), {K.key_index("fn")})


class MacroTests(unittest.TestCase):
    def test_factory_macro(self):
        from aula import macros as M
        raw = _backup("cmd_43.hex")
        ms = M.parse_store(raw)
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0].name, "M1")
        self.assertEqual([e.describe() for e in ms[0].events],
                         ["lctrl↓10ms", "grave↓10ms", "lctrl↑10ms", "grave↑10ms"])
        self.assertEqual(M.build_store(ms), raw)          # byte-for-byte round trip

    def test_steps(self):
        from aula import macros as M
        ev = M.parse_steps(["ctrl+c", "wait:100", "text:Hi"], delay=15)
        self.assertEqual([e.describe() for e in ev[:4]],
                         ["lctrl↓15ms", "c↓15ms", "c↑15ms", "lctrl↑115ms"])
        self.assertEqual(ev[4].describe(), "lshift↓15ms")  # capital H
        self.assertEqual(len(ev), 4 + 4 + 2)

    def test_store_layout_and_entry(self):
        from aula import macros as M
        store = M.build_store([M.Macro("a", M.parse_steps(["x"])), M.Macro("b", M.parse_steps(["y"]))])
        self.assertEqual(store[:4], bytes([8, 0, 11, 0]))  # 2 entries -> first macro at 8
        self.assertEqual(len(M.parse_store(store)), 2)
        self.assertEqual(M.macro_entry(1, M.REPEAT_TIMES, 3), bytes([3, 1, 3, 1]))
        with self.assertRaises(ValueError):
            M.parse_steps(["text:ç"])

    def test_store_skips_reserved_bytes(self):
        from aula import macros as M
        ms = [M.Macro("a", M.parse_steps(["text:" + "a" * 14])), M.Macro("b", M.parse_steps(["x"]))]
        store = M.build_store(ms)
        first = int.from_bytes(store[4:6], "little")
        self.assertEqual(first, 128)              # a: 8..123, b (11 bytes) would cross 126
        self.assertEqual(store[126:128], b"\0\0")
        self.assertEqual([m.name for m in M.parse_store(store)], ["a", "b"])

    def test_down_up_steps(self):
        from aula import macros as M
        ev = M.parse_steps(["down:shift", "a", "up:shift"])
        self.assertEqual([e.describe() for e in ev], ["lshift↓20ms", "a↓20ms", "a↑20ms", "lshift↑20ms"])

    def test_recording_to_steps(self):
        from aula import macros as M

        def rec(*keys, gap=30):
            out, t = [], 0
            for k in keys:
                name, down = k[1:], k[0] == "+"
                out.append((name, down, t))
                t += gap
            return out

        def tap(*names):
            return [x for n in names for x in (f"+{n}", f"-{n}")]

        # "Selam, iyi" + Enter on Turkish Q, then Ctrl+C and the Win key alone
        typed = rec("+lshift", *tap("s"), "-lshift", *tap("e", "l", "a", "m", "backslash", "space",
                                                           "quote", "y", "quote", "enter"),
                    "+lctrl", *tap("c"), "-lctrl", "+lwin", "-lwin")
        steps = M.steps_from_recording(typed, "tr")
        self.assertEqual(steps, ["text:Selam, iyi", "enter", "ctrl+c", "win"])
        self.assertEqual(M.steps_from_recording(typed, "us"), ["text:Selam\\ 'y'", "enter", "ctrl+c", "win"])

        def keys(events):
            return [(e.kind, e.code, e.down) for e in events]

        # replaying the steps gives the same characters (Shift released between letters is fine)
        replay = M.parse_steps(steps, layout="tr")
        self.assertEqual(sum(e.down for e in replay if e.kind == M.KIND_KEY), 12)

        # fast typing overlaps keys: still plain text (as recorded on hardware)
        fast = rec("+lshift", "+m", "-m", "-lshift", "+e", "+r", "-e", "-r", "+rshift", "+1", "-rshift", "-1")
        self.assertEqual(M.steps_from_recording(fast, "tr"), ["text:Mer!"])

        # a key really held while others are pressed falls back to down:/up:
        held = rec("+w", "+space", "-space", "-w", gap=200)
        steps = M.steps_from_recording(held)
        self.assertEqual(steps, ["down:w", "down:space", "up:space", "up:w"])
        self.assertEqual(keys(M.parse_steps(steps)), [(0, 0x1A, True), (0, 0x2C, True), (0, 0x2C, False), (0, 0x1A, False)])

        # pauses
        slow = [("a", True, 0), ("a", False, 30), ("b", True, 530), ("b", False, 560)]
        self.assertEqual(M.steps_from_recording(slow), ["text:ab"])
        self.assertEqual(M.steps_from_recording(slow, pauses=True), ["text:a", "wait:500", "text:b"])
        # spaces at the ends stay separate steps
        self.assertEqual(M.steps_from_recording(rec(*tap("space", "a", "space"))), ["space", "text:a", "space"])

    def test_text_layouts(self):
        from aula import macros as M

        def typed(text, layout):
            return [e.describe()[:-5] for e in M.parse_steps([f"text:{text}"], layout=layout) if e.down]

        self.assertEqual(typed("bilgi", "us"), ["b", "i", "l", "g", "i"])
        self.assertEqual(typed("bilgi", "tr"), ["b", "quote", "l", "g", "quote"])
        self.assertEqual(typed("ıİ", "tr"), ["i", "lshift", "quote"])
        self.assertEqual(typed("ğüşöç", "tr"), ["lbracket", "rbracket", "semicolon", "comma", "period"])
        self.assertEqual(typed(",.:", "tr"), ["backslash", "slash", "lshift", "slash"])
        self.assertEqual(typed("@<", "tr"), ["ralt", "q", "iso_backslash"])
        with self.assertRaises(ValueError):
            M.parse_steps(["text:ğ"], layout="us")


class PaletteTests(unittest.TestCase):
    def test_factory_palettes(self):
        raw = _backup("cmd_49.hex")
        self.assertEqual(len(raw), P.PALETTE_LEN)
        for hw in range(P.PALETTE_COUNT):
            self.assertEqual([P.palette_color(raw, hw, c) for c in range(7)], P.DEFAULT_PALETTE)

    def test_set_and_reset(self):
        raw = _backup("cmd_49.hex")
        changed = P.set_palette_color(raw, 2, 0, (255, 96, 0))   # breathing's red -> orange
        self.assertEqual(changed[2 * 21:2 * 21 + 3], bytes([255, 96, 0]))
        self.assertEqual(P.palette_color(changed, 1, 0), (255, 0, 0))   # static untouched
        self.assertEqual(changed[-7:], raw[-7:])                         # unknown tail kept
        self.assertEqual(P.reset_palette(changed, 2), raw)
        self.assertEqual(P.rgb_hex((255, 96, 0)), "#ff6000")
        for hw, color in ((23, 0), (1, 7)):
            with self.assertRaises(ValueError):
                P.palette_color(raw, hw, color)

    def test_preview_uses_palette(self):
        from aula import animation as A
        led = P.LedConfig(_backup("cmd_44.hex"))
        led.effect = 1
        led.set_slot(1, P.EffectSlot(9, 0, 0))
        pal = P.set_palette_color(_backup("cmd_49.hex"), 1, 0, (255, 96, 0))
        self.assertEqual(set(A.frame(led, 0.0, pal).values()), {(255, 96, 0)})


class PresetTests(unittest.TestCase):
    def test_synthwave(self):
        from aula import presets as T
        c = T.render(T.PRESET_BY_NAME["synthwave"])
        self.assertEqual(len(c), 80)                          # every key with a position
        self.assertEqual(c[K.key_index("esc")], (0xFF, 0x50, 0x00))
        self.assertEqual(c[K.key_index("w")], (0xFF, 0xFF, 0xFF))
        r, g, b = c[K.key_index("grave")]                      # left edge: purple
        self.assertTrue(r < 0x70 and g == 0 and b == 0xFF)
        self.assertEqual(c[K.key_index("pgup")], (0x00, 0xD5, 0xFF))    # rightmost: cyan

    def test_every_theme(self):
        from aula import presets as T
        self.assertEqual(len(T.PRESET_BY_NAME), len(T.PRESETS))  # unique names
        for p in T.PRESETS:
            self.assertEqual(len(T.render(p)), 80, p.name)

    def test_directions(self):
        from aula import presets as T
        fire = T.render(T.PRESET_BY_NAME["fire"])                # y: yellow on top, red at the bottom
        self.assertEqual(fire[K.key_index("f5")], (0xFF, 0xE0, 0x20))
        self.assertEqual(fire[K.key_index("space")], (0xFF, 0x00, 0x00))
        frost = T.render(T.PRESET_BY_NAME["frost"])              # diagonal: from the top left
        self.assertEqual(frost[K.key_index("esc")], (0xFF, 0xFF, 0xFF))  # accent
        self.assertEqual(frost[K.key_index("right")], (0x10, 0x30, 0xFF))
        nova = T.render(T.PRESET_BY_NAME["supernova"])           # center: bright middle, red edges
        self.assertGreater(sum(nova[K.key_index("h")]), sum(nova[K.key_index("grave")]))
        self.assertEqual(nova[K.key_index("esc")], (0xC0, 0x00, 0x10))


class LiveTests(unittest.TestCase):
    def test_frame(self):
        w, a, up = K.key_index("w"), K.key_index("a"), K.key_index("up")
        frame = P.live_frame({(255, 0, 0): [w, a], (0, 0, 255): [up], (0, 0, 0): [K.key_index("s")]})
        self.assertEqual(frame, bytes([255, 0, 0, 2, *sorted((w, a)), 0, 0, 255, 1, up]))  # black left out
        self.assertEqual(P.colors_from_live(frame), {w: (255, 0, 0), a: (255, 0, 0), up: (0, 0, 255)})

    def test_all_dark(self):
        self.assertEqual(P.live_frame({(0, 0, 0): [K.key_index("w")]}), bytes([0, 0, 0, 1, 0]))

    def test_every_animation_fits(self):
        from aula import live as L
        from aula import presets as T
        for anim in L.ANIMATIONS:
            for preset in (T.PRESETS if anim.uses_theme else T.PRESETS[:1]):
                for i in range(12):
                    t = 3 + i * 0.37
                    presses = L.demo_presses(t)
                    colors = anim.frame(preset, t, presses)
                    frame = L.frame(anim, preset, t, presses)
                    if anim.reactive:                    # full packets, see test_mixed_packets
                        self.assertEqual(len(frame) % P.CHUNK, 0, (anim.name, preset.name))
                        self.assertLessEqual(len(frame), P.LIVE_MAX, (anim.name, preset.name))
                    else:
                        self.assertLessEqual(len(frame), L.BUDGET, (anim.name, preset.name))
                    self.assertEqual(set(P.colors_from_live(frame)), {k for k, c in colors.items() if any(c)})

    def test_groups_stay_put(self):
        """Breathing only changes brightness, so every key keeps its group partners."""
        from aula import live as L
        from aula import presets as T
        preset = T.PRESET_BY_NAME["synthwave"]

        def partners(t):
            frame = L.frame(L.ANIMATION_BY_NAME["breathe"], preset, t)
            groups, i = [], 0
            while i < len(frame):
                groups.append(frozenset(frame[i + 4:i + 4 + frame[i + 3]]))
                i += 4 + frame[i + 3]
            return set(groups)

        self.assertEqual(partners(0.4), partners(1.9))

    def test_accents_keep_their_color(self):
        from aula import live as L
        from aula import presets as T
        for name in ("synthwave", "dracula", "volcano"):
            preset = T.PRESET_BY_NAME[name]
            for t in (0.3, 1.1, 2.6):
                shown = P.colors_from_live(L.frame(L.ANIMATION_BY_NAME["wave"], preset, t))
                for key, rgb in preset.accents.items():
                    self.assertEqual(shown[K.key_index(key)], rgb, (name, key))

    def test_median_cut(self):
        import random
        rng = random.Random(1)
        groups = {tuple(rng.randrange(256) for _ in range(3)): [i] for i in range(60)}
        merged = P.median_cut(groups, 10)
        self.assertLessEqual(len(merged), 10)
        self.assertEqual(sorted(i for ks in merged.values() for i in ks), list(range(60)))


class ReactiveTests(unittest.TestCase):
    """Animations that light up the keys you press."""

    @classmethod
    def setUpClass(cls):
        from aula import live as L
        from aula import presets as T
        cls.L, cls.theme = L, T.PRESET_BY_NAME["ocean"]

    def shown(self, name, t, presses):
        L = self.L
        return P.colors_from_live(L.frame(L.ANIMATION_BY_NAME[name], self.theme, t, presses))

    def resting(self):
        return self.shown("ripple", 5.0, [])

    def test_quiet_without_presses(self):
        for name in ("ripple", "afterglow", "heatmap"):
            self.assertEqual(self.shown(name, 5.0, []), self.resting(), name)

    def test_ripple_travels(self):
        g, far = K.key_index("g"), K.key_index("enter")      # Enter is about 7.6 keys from G
        rest = self.resting()
        press = [(g, 1.0)]
        early, later = self.shown("ripple", 1.05, press), self.shown("ripple", 2.1, press)
        self.assertGreater(sum(early[g]), sum(rest[g]))      # starts at the key
        self.assertEqual(early[far], rest[far])
        self.assertGreater(sum(later[far]), sum(rest[far]))  # and reaches Enter later
        self.assertEqual(self.shown("ripple", 2.6, press), rest)   # then it is gone

    def test_afterglow_fades(self):
        h = K.key_index("h")                                  # not an accent key of the theme
        press = [(h, 1.0)]
        glow = [sum(self.shown("afterglow", 1.0 + dt, press)[h]) for dt in (0.05, 0.8, 1.6)]
        self.assertGreater(glow[0], glow[1])
        self.assertGreater(glow[1], glow[2])
        self.assertGreater(glow[2], sum(self.resting()[h]))
        self.assertEqual(self.shown("afterglow", 4.5, press), self.resting())

    def test_heatmap_warms_up(self):
        e, r = K.key_index("e"), K.key_index("r")
        once = self.shown("heatmap", 2.0, [(e, 1.0)])
        often = self.shown("heatmap", 2.0, [(e, 1.0), (e, 1.2), (e, 1.4), (e, 1.6)])
        self.assertGreater(sum(once[e]), sum(self.resting()[e]))
        self.assertGreater(sum(often[e]), sum(once[e]))      # hotter = the theme's brighter tone
        self.assertNotEqual(often[r], self.resting()[r])     # the heat spreads to the neighbours

    def test_resting_keys_keep_their_groups(self):
        """Typing must not move the keys that aren't lit between groups (that flickers)."""
        L = self.L
        anim = L.ANIMATION_BY_NAME["ripple"]

        def partners(t):
            frame, groups, i = L.frame(anim, self.theme, t, L.demo_presses(t)), {}, 0
            while i < len(frame):
                keys = frozenset(frame[i + 4:i + 4 + frame[i + 3]])
                for k in keys:
                    groups[k] = keys
                i += 4 + frame[i + 3]
            return groups

        quiet = partners(0.0)                                 # no key pressed yet: all resting
        busy = partners(6.0)
        lit = {k for k, ks in busy.items() if ks not in quiet.values()}
        for k, ks in busy.items():
            if k not in lit:
                self.assertEqual(ks - lit, quiet[k] - lit, k)

    def test_resting_keys_never_change(self):
        """Keys that aren't lit look exactly as at rest, whatever is lit elsewhere
        (any change there shows as flicker). (A lit key may rest when too many are
        lit for one frame: the faintest give way.)"""
        from aula import presets as T
        L = self.L
        for name in ("ripple", "afterglow", "heatmap"):
            anim = L.ANIMATION_BY_NAME[name]
            for preset in (T.PRESET_BY_NAME[n] for n in ("ocean", "synthwave", "dracula")):
                rest = P.colors_from_live(L.frame(anim, preset, 0.0, []))
                for i in range(10):
                    t = 3 + i * 0.29
                    presses = L.demo_presses(t)
                    colors = anim.frame(preset, t, presses)
                    shown = P.colors_from_live(L.frame(anim, preset, t, presses))
                    for k, c in colors.items():
                        if c == L._resting(preset)[k]:
                            self.assertEqual(shown[k], rest[k], (name, preset.name, t, k))

    def test_mixed_packets(self):
        """After a lost packet the keyboard fills the gap from the next frame. Any mix
        of two frames' packets must still read as valid groups showing colors that
        one of the frames really has (a misread showed keys yellow in ocean)."""
        import random
        from aula import presets as T
        L, rng = self.L, random.Random(5)
        valid = {idx for idx, *_ in K.KEYS} - {K.BY_NAME["knob"]}
        for name in ("ripple", "afterglow", "heatmap"):
            anim = L.ANIMATION_BY_NAME[name]
            for preset in (T.PRESET_BY_NAME[n] for n in ("ocean", "synthwave", "dracula")):
                for i in range(12):
                    t = 3 + i * 0.37
                    a = L.frame(anim, preset, t, L.demo_presses(t))
                    b = L.frame(anim, preset, t + 0.09, L.demo_presses(t + 0.09))
                    self.assertEqual(len(a), len(b))      # the same packet count every frame
                    colors = set()                        # every group color either frame sends
                    for frame in (a, b):
                        j = 0
                        while j < len(frame):
                            colors.add(tuple(frame[j:j + 3]))
                            j += 4 + frame[j + 3]
                    pa = [a[n:n + P.CHUNK] for n in range(0, len(a), P.CHUNK)]
                    pb = [b[n:n + P.CHUNK] for n in range(0, len(b), P.CHUNK)]
                    mixed = b"".join(rng.choice(pair) for pair in zip(pa, pb))
                    j = 0
                    while j < len(mixed):                 # strict read: whole groups, real keys
                        count = mixed[j + 3]
                        self.assertGreater(count, 0)
                        self.assertLessEqual(j + 4 + count, len(mixed))
                        self.assertTrue(set(mixed[j + 4:j + 4 + count]) <= valid)
                        self.assertIn(tuple(mixed[j:j + 3]), colors)
                        j += 4 + count
                    self.assertEqual(set(P.colors_from_live(mixed)), set(P.colors_from_live(a)))

    def test_demo_typing(self):
        L = self.L
        presses = L.demo_presses(10.0)
        self.assertEqual(presses, L.demo_presses(10.0))      # the same every time
        self.assertEqual([at for _, at in presses], sorted(at for _, at in presses))
        self.assertTrue(all(at <= 10.0 for _, at in presses))
        self.assertEqual(L.demo_presses(10.0)[:-3], L.demo_presses(10.9)[:len(presses) - 3])

    def test_animate_command(self):
        """`aula animate ripple` with a stand-in keyboard: key presses come back lit."""
        import argparse
        import contextlib
        import io

        from aula import cli
        g = K.key_index("g")

        class FakeKeyboard:
            def __init__(self):
                self.frames, self.calls = [], 0

            def key_presses(self):
                self.calls += 1
                return [g] if self.calls == 3 else []        # the 1st call drops old presses

            def send_live(self, frame):
                self.frames.append(P.colors_from_live(frame))

        kb = FakeKeyboard()
        with contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_animate(kb, argparse.Namespace(name="ripple", theme="ocean", speed=1.0, seconds=0.3))
        rest = self.resting()
        self.assertEqual(kb.frames[0], rest)                  # nothing pressed yet
        self.assertTrue(any(f[g] != rest[g] for f in kb.frames[1:]))


class MatrixTests(unittest.TestCase):
    def test_backup_matches_keymap(self):
        m = _backup("cmd_41.hex")
        self.assertEqual(P.matrix_entry(m, K.key_index("esc")), P.key_entry(hid=K.HID["esc"]))
        self.assertEqual(P.matrix_entry(m, K.key_index("q")), P.key_entry(hid=K.HID["q"]))
        self.assertEqual(P.matrix_entry(m, K.key_index("lshift")),
                         P.key_entry(modifiers=K.MODIFIERS["lshift"]))
        self.assertEqual(P.matrix_entry(m, K.key_index("ralt")),
                         P.key_entry(modifiers=K.MODIFIERS["ralt"]))

    def test_tr_alias(self):
        self.assertEqual(K.key_index("ğ"), K.key_index("lbracket"))
        self.assertEqual(K.key_index("#53"), 53)


if __name__ == "__main__":
    unittest.main()
