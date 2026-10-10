"""macOS backend: pure logic everywhere, real hidapi / Quartz calls on macOS (no keyboard needed)."""

import ctypes
import os
import subprocess
import sys
import unittest

from aula import keymap as K
from aula import macros as M
from aula.backends import macos as MAC

ON_MAC = sys.platform == "darwin"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def entry(pid, page=0xFF02, usage=2, vid=0x3554):
    return {"path": f"DevSrvsID:{vid:x}{pid:x}{page:x}{usage}".encode(), "vendor_id": vid,
            "product_id": pid, "usage_page": page, "usage": usage,
            "product_string": "Compx 2.4G Wireless Receiver", "interface_number": 1}


class FakeEvent:
    def __init__(self, keycode):
        self.hardware_keycode = keycode


class PickTests(unittest.TestCase):
    def test_vendor_collection_only(self):
        found = MAC.pick_devices([entry(0xFA09, page=1, usage=6), entry(0xFA09, page=0x0C, usage=1),
                                  entry(0xFA09)])
        self.assertEqual([(d["mode"], d["supported"]) for d in found], [("2.4G dongle", True)])
        self.assertIsInstance(found[0]["path"], str)

    def test_bluetooth_and_wired(self):
        found = MAC.pick_devices([entry(0xFA07), entry(0x010C, vid=0x258A, page=0xFF00, usage=1),
                                  entry(0x010C, vid=0x258A, page=1, usage=6)])
        self.assertEqual([(d["mode"], d["supported"]) for d in found],
                         [("Bluetooth", True), ("wired", False)])


class LayoutTests(unittest.TestCase):
    def test_source_ids(self):
        self.assertEqual(MAC.layout_from_source_id("com.apple.keylayout.Turkish-QWERTY-PC"), "tr_mac_pc")
        self.assertEqual(MAC.layout_from_source_id("com.apple.keylayout.Turkish-QWERTY"), "tr_mac")
        self.assertEqual(MAC.layout_from_source_id("com.apple.keylayout.Turkish"), "us")  # F
        self.assertEqual(MAC.layout_from_source_id("com.apple.keylayout.ABC"), "us")
        self.assertEqual(MAC.layout_from_source_id(""), "us")

    def test_mac_tables(self):
        def keys(text, layout):
            return [e.describe()[:-5] for e in M.parse_steps([f"text:{text}"], layout=layout) if e.down]

        self.assertEqual(keys("iı", "tr_mac"), ["quote", "i"])
        self.assertEqual(keys("ğüşöç", "tr_mac"), ["lbracket", "rbracket", "semicolon", "comma", "period"])
        self.assertEqual(keys(",.", "tr_mac_pc"), ["backslash", "slash"])
        for text, layout in (("a,b", "tr_mac"), ("@", "tr_mac_pc")):  # left out on purpose
            with self.assertRaises(ValueError):
                M.parse_steps([f"text:{text}"], layout=layout)


class RecordingTests(unittest.TestCase):
    def test_names_are_known(self):
        self.assertLessEqual(set(MAC.KEYCODES.values()), set(K.HID) | set(M.MOD_CODES))

    def test_key_name(self):
        self.assertEqual(MAC.key_name(FakeEvent(0x00)), "a")
        self.assertEqual(MAC.key_name(FakeEvent(0x37)), "lwin")    # Command
        self.assertEqual(MAC.key_name(FakeEvent(0x3D)), "ralt")    # right Option
        self.assertEqual(MAC.key_name(FakeEvent(0x7B)), "left")
        self.assertIsNone(MAC.key_name(FakeEvent(0x3F)))           # Fn

    def test_every_letter_and_digit(self):
        names = set(MAC.KEYCODES.values())
        self.assertLessEqual(set("abcdefghijklmnopqrstuvwxyz0123456789"), names)
        self.assertLessEqual({f"f{i}" for i in range(1, 13)}, names)


class ScriptTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "needs a POSIX shell")
    def test_install_script_parses(self):
        r = subprocess.run(["sh", "-n", os.path.join(ROOT, "install-macos.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


@unittest.skipUnless(ON_MAC, "needs macOS")
class MacTests(unittest.TestCase):
    def test_enumeration_runs(self):
        try:
            import hid  # noqa: F401
        except ImportError:
            self.skipTest("hidapi not installed")
        self.assertIsInstance(MAC.find_devices(), list)   # no keyboard on CI: empty, no crash

    def test_open_shared(self):
        try:
            import hid
        except ImportError:
            self.skipTest("hidapi not installed")
        MAC.open_shared(hid)
        self.assertEqual(ctypes.CDLL(hid.__file__).hid_darwin_get_open_exclusive(), 0)

    def test_key_guard(self):
        MAC.MacKeyGuard().wait_released(quiet=0.05, limit=2.0)

    def test_layout(self):
        self.assertIn(MAC.detect_layout(), M.LAYOUTS)


if __name__ == "__main__":
    unittest.main()
