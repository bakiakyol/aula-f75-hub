"""GTK 3 interface for the AULA F75 configuration tool.

Start with:  ./aula.sh gui   (or python3 -m aula gui)
"""

import math
import os
import queue
import threading
import traceback

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import animation as A  # noqa: E402
from . import backends  # noqa: E402
from . import keymap as K  # noqa: E402
from . import macros as M  # noqa: E402
from . import presets as T  # noqa: E402
from . import protocol as P  # noqa: E402
from .cli import BACKUP, delete_macro  # noqa: E402
from .device import AulaError, Keyboard  # noqa: E402

CUSTOM_HW = P.EFFECT_BY_NAME["custom"].hw

# The board is drawn as a lit object on a dark desk: light needs darkness to show.
DESK = (0.063, 0.067, 0.086)       # #101116 night desk
PLATE = (0.106, 0.114, 0.133)      # #1B1D22 graphite plate
PLATE_EDGE = (0.17, 0.18, 0.21)
CAP = (58, 61, 69)                 # #3A3D45 unlit keycap
UNLIT = (44, 47, 54)               # how an unlit key is drawn on the board


CSS = b"""
.desk { background-color: #101116; }
.desk label { color: #8b92a0; }
.readout { font-family: "Ubuntu Sans Mono", Consolas, Menlo, monospace; font-size: 9pt; letter-spacing: 1px; }
.readout.value { color: #d7dae0; }
.desk button {
    background-image: none; background-color: #1b1d22; color: #d7dae0;
    border: 1px solid #2b2e36; box-shadow: none; text-shadow: none; -gtk-icon-shadow: none;
}
.desk button:hover { background-color: #252830; }
.desk button.swatch { padding: 3px; border-radius: 7px; }
"""


UI_FONT = "Ubuntu Sans,Segoe UI,Helvetica Neue,sans"  # first one installed wins
KNOB_RECT = (605, 30, 630, 57)  # drawn top right, next to F12
ORIGINAL_BACKUP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup")

SWATCHES = [
    ("Red", (255, 0, 0)), ("Orange", (255, 80, 0)), ("Yellow", (255, 200, 0)),
    ("Green", (0, 255, 0)), ("Cyan", (0, 213, 255)), ("Blue", (0, 0, 255)),
    ("Purple", (96, 0, 255)), ("Pink", (255, 0, 144)), ("White", (255, 255, 255)),
    ("Off", (0, 0, 0)),
]


def readout(led: P.LedConfig, selected: int, palette: bytes | None = None) -> tuple[str, str]:
    """Left/right text of the instrument strip under the board (real values only)."""
    hw = led.effect
    e = P.EFFECT_BY_HW.get(hw)
    parts = [(e.name if e else f"effect {hw}").upper()]
    if hw == CUSTOM_HW:
        parts.append("YOUR KEY COLORS")
    elif 1 <= hw <= P.LED_SLOTS:
        slot = led.slot(hw)
        if e is None or e.color:
            name = P.COLORS[slot.color].upper() if slot.color < len(P.COLORS) else str(slot.color)
            if palette is not None and slot.color < P.PALETTE_COLORS and hw < P.PALETTE_COUNT:
                rgb = P.palette_color(palette, hw, slot.color)
                if rgb != P.DEFAULT_PALETTE[slot.color]:
                    name = P.rgb_hex(rgb).upper()
            parts.append(name)
        parts.append(f"BRIGHTNESS {slot.brightness}/9")
        if e is None or e.speed:
            parts.append(f"SPEED {slot.speed}/4")
        if hw in A.REACTIVE:
            parts.append("DEMO OF KEY PRESSES")
        elif A.is_animated(led):
            parts.append("APPROXIMATE PREVIEW")
    if selected:
        right = f"{selected} SELECTED"
        if hw != CUSTOM_HW:
            right += " · PAINTING SWITCHES TO CUSTOM"
    else:
        right = "CLICK KEYS TO PAINT · CTRL+CLICK ADDS"
    return "  ·  ".join(parts), right


def _key_rect(idx: int, rect: tuple) -> tuple:
    return KNOB_RECT if idx == K.BY_NAME["knob"] else rect


def describe_entry(entry: bytes) -> str:
    """Human-readable form of a 4-byte keymap entry."""
    kind, mods, _, hid = entry
    if entry == b"\0\0\0\0":
        return "none"
    if kind == 0:
        parts = [n for n, bit in K.MODIFIERS.items() if mods & bit]
        if hid:
            names = [n for n, code in K.HID.items() if code == hid]
            parts.append(names[0] if names else f"0x{hid:02x}")
        return " + ".join(parts)
    return f"special ({entry.hex(' ')})"


def _once(cb, arg):
    """GLib.idle_add callback wrapper: run once (a truthy return would repeat it)."""
    cb(arg)
    return False


class Worker:
    """Runs keyboard operations on a background thread, one at a time.

    Jobs submitted with the same `key` are coalesced: only the newest one runs,
    so dragging a slider sends just the final value.
    """

    def __init__(self, on_error):
        self.q: queue.Queue = queue.Queue()
        self.latest: dict[str, int] = {}
        self.seq = 0
        self.kb: Keyboard | None = None
        self.on_error = on_error
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, fn, done=None, key=None):
        self.seq += 1
        if key:
            self.latest[key] = self.seq
        self.q.put((self.seq, key, fn, done))

    def _run(self):
        while True:
            seq, key, fn, done = self.q.get()
            if key and self.latest.get(key) != seq:
                continue
            try:
                if self.kb is None:
                    self.kb = Keyboard()
                result = fn(self.kb)
            except Exception as e:  # noqa: BLE001 - an escaping error would kill this thread
                msg = str(e)
                if not isinstance(e, (AulaError, OSError, ValueError)):
                    traceback.print_exc()
                    msg = f"{type(e).__name__}: {e}"
                if self.kb is not None:
                    try:
                        self.kb.close()
                    except OSError:
                        pass
                self.kb = None
                GLib.idle_add(_once, self.on_error, msg)
                continue
            if done:
                GLib.idle_add(_once, done, result)


class KeyboardView(Gtk.DrawingArea):
    """Drawing of the board; click to select keys (Ctrl/Shift-click adds)."""

    MARGIN = 22

    def __init__(self, on_select):
        super().__init__()
        self.colors: dict[int, tuple] = {}     # custom effect table (what painting edits)
        self.preview: dict[int, tuple] | None = None  # shown instead while another effect runs
        self.selected: set[int] = set()
        self.on_select = on_select
        self.set_size_request(640, 260)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._click)

    def _geometry(self):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        x0, y0, x1, y1 = 30, 30, 630, 263
        s = min((w - 2 * self.MARGIN) / (x1 - x0), (h - 2 * self.MARGIN) / (y1 - y0))
        ox = (w - (x1 - x0) * s) / 2 - x0 * s
        oy = (h - (y1 - y0) * s) / 2 - y0 * s
        return s, ox, oy

    @staticmethod
    def _rounded(cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -1.5708, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
        cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
        cr.arc(x + r, y + r, r, 3.1416, 4.7124)
        cr.close_path()

    def _draw(self, _w, cr):
        s, ox, oy = self._geometry()
        shown = self.preview if self.preview is not None else self.colors
        knob = K.BY_NAME["knob"]

        cr.set_source_rgb(*DESK)
        cr.paint()
        # case: soft vertical gradient with a lit top edge
        cx, cy, cw, ch = ox + 16 * s, oy + 16 * s, 628 * s, 261 * s
        self._rounded(cr, cx, cy + 4 * s, cw, ch, 16 * s)         # case shadow on the desk
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.fill()
        case = cairo.LinearGradient(0, cy, 0, cy + ch)
        case.add_color_stop_rgb(0, 0.17, 0.18, 0.21)
        case.add_color_stop_rgb(1, 0.10, 0.105, 0.12)
        self._rounded(cr, cx, cy, cw, ch, 16 * s)
        cr.set_source(case)
        cr.fill()
        cr.move_to(cx + 16 * s, cy + 0.8)
        cr.line_to(cx + cw - 16 * s, cy + 0.8)
        cr.set_source_rgba(1, 1, 1, 0.12)
        cr.set_line_width(1)
        cr.stroke()
        # recessed plate the keys sit in
        px, py, pw, ph = ox + 24 * s, oy + 24 * s, 612 * s, 245 * s
        self._rounded(cr, px, py, pw, ph, 9 * s)
        cr.set_source_rgb(0.045, 0.048, 0.058)
        cr.fill()

        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription(f"{UI_FONT} Medium {max(6.5, 7.2 * s):.1f}"))
        for idx, _name, label, rect in K.KEYS:
            x1, y1, x2, y2 = _key_rect(idx, rect)
            x, y, w, h = ox + x1 * s, oy + y1 * s, (x2 - x1) * s, (y2 - y1) * s
            if idx == knob:
                self._draw_knob(cr, x, y, w, s)
                continue
            r, g, b = (c / 255 for c in shown.get(idx, (0, 0, 0)))
            lit = r + g + b > 0.1
            rad = 4 * s
            if lit:
                # light leaking from under the cap: a crisp rim, strongest at the bottom edge
                self._rounded(cr, x - 1.6 * s, y - 0.6 * s, w + 3.2 * s, h + 3.0 * s, rad + 1.6 * s)
                cr.set_source_rgba(r, g, b, 0.28)
                cr.fill()
                self._rounded(cr, x - 0.8 * s, y + 0.4 * s, w + 1.6 * s, h + 1.6 * s, rad + 0.8 * s)
                cr.set_source_rgba(r, g, b, 0.85)
                cr.fill()
            # dark matte cap, slightly convex, faintly tinted by the light underneath
            tint = 0.22 if lit else 0
            cap = cairo.LinearGradient(0, y, 0, y + h)
            cap.add_color_stop_rgb(0, *(0.20 + (c - 0.20) * tint for c in (r, g, b)))
            cap.add_color_stop_rgb(1, *(0.115 + (c - 0.115) * tint * 0.6 for c in (r, g, b)))
            self._rounded(cr, x, y, w, h, rad)
            cr.set_source(cap)
            cr.fill()
            # dished top face
            self._rounded(cr, x + 2.2 * s, y + 1.4 * s, w - 4.4 * s, h - 5 * s, rad * 0.8)
            cr.set_source_rgba(1, 1, 1, 0.035)
            cr.fill()
            cr.move_to(x + rad, y + 0.8)
            cr.line_to(x + w - rad, y + 0.8)
            cr.set_source_rgba(1, 1, 1, 0.14)
            cr.set_line_width(1)
            cr.stroke()
            if idx in self.selected:
                self._rounded(cr, x - 2.5 * s, y - 2.5 * s, w + 5 * s, h + 5 * s, rad + 2.5 * s)
                cr.set_source_rgb(1, 1, 1)
                cr.set_line_width(max(1.5, 1.8 * s))
                cr.stroke()
            # legend glows in the key's color (shine-through)
            if lit:
                legend = tuple(min(1.0, c * 0.6 + 0.4) for c in (r, g, b))
            else:
                legend = (0.42, 0.44, 0.50)
            layout.set_text(label, -1)
            lw, lh = layout.get_pixel_size()
            lx, ly = x + (w - lw) / 2, y + (h - 1.5 * s - lh) / 2
            if lit:
                cr.set_source_rgba(*legend, 0.35)              # faint halo behind the glyphs
                for dx, dy in ((-0.8, 0), (0.8, 0), (0, -0.8), (0, 0.8)):
                    cr.move_to(lx + dx, ly + dy)
                    PangoCairo.show_layout(cr, layout)
            cr.set_source_rgb(*legend)
            cr.move_to(lx, ly)
            PangoCairo.show_layout(cr, layout)

    def _draw_knob(self, cr, x, y, w, s):
        cx, cy, r = x + w / 2, y + w / 2, w / 2
        cr.new_path()
        grad = cairo.RadialGradient(cx - r * 0.35, cy - r * 0.45, r * 0.1, cx, cy, r)
        grad.add_color_stop_rgb(0, 0.78, 0.80, 0.84)
        grad.add_color_stop_rgb(1, 0.30, 0.31, 0.35)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source(grad)
        cr.fill_preserve()
        cr.set_source_rgb(*(c * 0.6 for c in (0.30, 0.31, 0.35)))
        cr.set_line_width(1)
        cr.stroke()
        cr.set_line_width(max(1.0, 1.2 * s))            # knurling around the edge
        cr.set_source_rgba(0, 0, 0, 0.35)
        for i in range(24):
            a = i * 2 * math.pi / 24
            cr.move_to(cx + math.cos(a) * r * 0.82, cy + math.sin(a) * r * 0.82)
            cr.line_to(cx + math.cos(a) * r * 0.98, cy + math.sin(a) * r * 0.98)
        cr.stroke()
        if K.BY_NAME["knob"] in self.selected:
            cr.arc(cx, cy, r + 2 * s, 0, 2 * math.pi)
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(max(1.5, 2 * s))
            cr.stroke()

    def _click(self, _w, event):
        s, ox, oy = self._geometry()
        px, py = (event.x - ox) / s, (event.y - oy) / s
        hit = None
        for idx, _name, _label, rect in K.KEYS:
            x1, y1, x2, y2 = _key_rect(idx, rect)
            if x1 <= px <= x2 and y1 <= py <= y2:
                hit = idx
                break
        add = event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
        if hit is None:
            if not add:
                self.selected.clear()
        elif add:
            self.selected ^= {hit}
        else:
            self.selected = {hit}
        self.queue_draw()
        self.on_select()


class AulaWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="AULA F75")
        self.set_default_size(980, 680)
        self.led: P.LedConfig | None = None
        self.palette: bytes | None = None  # effect palettes (0x49)
        self.updating = False  # True while widgets are filled from device state
        self.worker = Worker(self.show_error)
        self.recording: list[tuple[str, bool, int]] | None = None  # macro recording in progress
        self.rec_held: set[str] = set()
        self.rec_skipped = 0
        self.connect("key-press-event", self.on_record_key)
        self.connect("key-release-event", self.on_record_key)

        header = Gtk.HeaderBar(title="AULA F75", show_close_button=True)
        header.set_subtitle("connecting…")
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Reload from keyboard")
        refresh.connect("clicked", lambda _b: self.load())
        header.pack_start(refresh)
        self.header = header
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        desk = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        desk.get_style_context().add_class("desk")
        self.view = KeyboardView(self.on_selection)
        desk.pack_start(self.view, True, True, 0)
        desk.pack_start(self._desk_tools(), False, False, 0)
        root.pack_start(desk, True, True, 0)

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        stack.add_titled(self._page_lighting(), "lighting", "Lighting")
        stack.add_titled(self._page_remap(), "remap", "Key remap")
        stack.add_titled(self._page_macros(), "macros", "Macros")
        stack.add_titled(self._page_device(), "device", "Device")
        stack.add_titled(self._page_backup(), "backup", "Backup")
        sidebar = Gtk.StackSidebar(stack=stack)
        sidebar.set_size_request(160, -1)
        bottom = Gtk.Box()
        bottom.pack_start(sidebar, False, False, 0)
        bottom.pack_start(stack, True, True, 0)
        root.pack_start(bottom, False, False, 0)

        self.status = Gtk.Label(xalign=0, margin=6)
        self.status.get_style_context().add_class("dim-label")
        root.pack_start(self.status, False, False, 0)

        self.t0 = GLib.get_monotonic_time()
        GLib.timeout_add(50, self.tick)
        self.connect("destroy", Gtk.main_quit)
        self.load()

    # ------------------------------------------------------------ widgets
    @staticmethod
    def _grid():
        g = Gtk.Grid(column_spacing=12, row_spacing=10, margin=16)
        return g

    @staticmethod
    def _label(text):
        return Gtk.Label(label=text, xalign=1)

    def _desk_tools(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=20,
                        margin_end=20, margin_bottom=14)
        strip = Gtk.Box(spacing=12)
        self.readout_left = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.readout_right = Gtk.Label(xalign=1)
        for lbl in (self.readout_left, self.readout_right):
            lbl.get_style_context().add_class("readout")
        self.readout_left.get_style_context().add_class("value")
        strip.pack_start(self.readout_left, True, True, 0)
        strip.pack_end(self.readout_right, False, False, 0)
        outer.pack_start(strip, False, False, 0)

        box = Gtk.Box(spacing=6)
        outer.pack_start(box, False, False, 0)
        for name, rgb in SWATCHES:
            btn = Gtk.Button()
            btn.get_style_context().add_class("swatch")
            btn.set_tooltip_text(f"Paint selected keys {name.lower()}")
            area = Gtk.DrawingArea()
            area.set_size_request(24, 18)
            area.connect("draw", self._draw_swatch, rgb)
            btn.add(area)
            btn.connect("clicked", lambda _b, c=rgb: self.paint_selection(c))
            box.pack_start(btn, False, False, 0)
        picker = Gtk.Button(label="Custom color…")
        picker.set_tooltip_text("Paint selected keys with any color")
        picker.connect("clicked", self.on_color_picked)
        box.pack_start(picker, False, False, 0)
        clear = Gtk.Button(label="Clear selection")
        clear.connect("clicked", self.on_clear_selection)
        box.pack_end(clear, False, False, 0)
        sel_all = Gtk.Button(label="Select all")
        sel_all.connect("clicked", self.on_select_all)
        box.pack_end(sel_all, False, False, 0)
        return outer

    @staticmethod
    def _draw_swatch(_w, cr, rgb):
        w, h = _w.get_allocated_width(), _w.get_allocated_height()
        KeyboardView._rounded(cr, 0, 0, w, h, 4)
        if rgb == (0, 0, 0):                          # "off": an unlit cap with a slash
            cr.set_source_rgb(*(c / 255 for c in CAP))
            cr.fill()
            cr.set_source_rgb(0.55, 0.57, 0.63)
            cr.set_line_width(1.5)
            cr.move_to(4, h - 4)
            cr.line_to(w - 4, 4)
            cr.stroke()
        else:
            cr.set_source_rgb(*(c / 255 for c in rgb))
            cr.fill()
        return True

    def _page_lighting(self):
        g = self._grid()
        self.effect_combo = Gtk.ComboBoxText()
        for e in P.EFFECTS:
            self.effect_combo.append(str(e.hw), f"{e.name}  ({e.hw})")
        self.effect_combo.connect("changed", self.on_led_widget)
        self.color_combo = Gtk.ComboBoxText()
        for i, c in enumerate(P.COLORS):
            self.color_combo.append(str(i), c)
        self.color_combo.connect("changed", self.on_led_widget)
        self.color_rgb = Gtk.ColorButton(use_alpha=False)
        self.color_rgb.set_tooltip_text("Any color: replaces the chosen color for this effect")
        self.color_rgb.connect("color-set", self.on_effect_rgb)
        self.color_reset = Gtk.Button(label="Factory colors")
        self.color_reset.set_tooltip_text("Put this effect's 7 factory colors back")
        self.color_reset.connect("clicked", self.on_effect_colors_reset)
        color_row = Gtk.Box(spacing=6)
        color_row.pack_start(self.color_combo, True, True, 0)
        color_row.pack_start(self.color_rgb, False, False, 0)
        color_row.pack_start(self.color_reset, False, False, 0)
        self.bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 9, 1)
        self.speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 4, 1)
        for sc in (self.bright, self.speed):
            sc.set_digits(0)
            sc.set_hexpand(True)
            sc.connect("value-changed", self.on_led_widget)
        rows = [("Effect", self.effect_combo), ("Color", color_row),
                ("Brightness", self.bright), ("Speed", self.speed)]
        for r, (text, w) in enumerate(rows):
            g.attach(self._label(text), 0, r, 1, 1)
            g.attach(w, 1, r, 1, 1)
        presets = Gtk.Box(spacing=6)
        for p in T.PRESETS:
            b = Gtk.Button(label=p.name)
            b.set_tooltip_text(p.description)
            b.connect("clicked", lambda _b, p=p: self.load_preset(p))
            presets.pack_start(b, False, False, 0)
        g.attach(self._label("Themes"), 0, len(rows), 1, 1)
        g.attach(presets, 1, len(rows), 1, 1)
        return g

    def _page_remap(self):
        g = self._grid()
        self.remap_key = Gtk.Label(label="Click a key on the drawing above", xalign=0)
        self.remap_layer = Gtk.ComboBoxText()
        self.remap_layer.append("0", "Base layer")
        self.remap_layer.append("1", "Fn layer")
        self.remap_layer.set_active_id("0")
        self.remap_layer.connect("changed", lambda _c: self.show_mapping())
        self.remap_current = Gtk.Label(label="–", xalign=0)
        self.remap_target = Gtk.ComboBoxText()
        self.remap_target.append("none", "none (disable key)")
        for name in K.MODIFIERS:
            self.remap_target.append(name, name)
        for name in sorted(K.HID, key=lambda n: K.HID[n]):
            self.remap_target.append(name, name)
        apply = Gtk.Button(label="Apply")
        apply.get_style_context().add_class("suggested-action")
        apply.connect("clicked", self.on_remap)
        restore = Gtk.Button(label="Restore original")
        restore.set_tooltip_text("Put back this key's factory mapping")
        restore.connect("clicked", self.on_remap_restore)
        buttons = Gtk.Box(spacing=6)
        buttons.pack_start(apply, False, False, 0)
        buttons.pack_start(restore, False, False, 0)
        rows = [("Key", self.remap_key), ("Layer", self.remap_layer),
                ("Currently", self.remap_current), ("New function", self.remap_target),
                ("", buttons)]
        for r, (text, w) in enumerate(rows):
            g.attach(self._label(text), 0, r, 1, 1)
            g.attach(w, 1, r, 1, 1)
        return g

    def _page_device(self):
        g = self._grid()
        self.side_combo = Gtk.ComboBoxText()
        for i, m in enumerate(P.SIDE_MODES):
            self.side_combo.append(str(i), m)
        self.knob_combo = Gtk.ComboBoxText()
        self.knob_combo.append("0", "media (volume, mute)")
        self.knob_combo.append("1", "lighting (brightness, next effect)")
        self.os_combo = Gtk.ComboBoxText()
        for i, m in enumerate(P.OS_MODES):
            self.os_combo.append(str(i), m)
        for c in (self.side_combo, self.knob_combo, self.os_combo):
            c.connect("changed", self.on_led_widget)
        self.sleep_combo = Gtk.ComboBoxText()
        self.sleep_combo.set_tooltip_text("Idle time before the keyboard sleeps (2.4G and Bluetooth)")
        self.sleep_combo.connect("changed", self.on_led_widget)
        self.winlock = Gtk.Switch(halign=Gtk.Align.START)
        self.winlock.connect("notify::active", self.on_led_widget)
        rows = [("Side light", self.side_combo), ("Knob", self.knob_combo),
                ("OS mode", self.os_combo), ("Windows key lock", self.winlock),
                ("Sleep after", self.sleep_combo)]
        for r, (text, w) in enumerate(rows):
            g.attach(self._label(text), 0, r, 1, 1)
            g.attach(w, 1, r, 1, 1)
        return g

    def _page_macros(self):
        g = self._grid()
        self.macro_list: list[M.Macro] = []
        self.macro_combo = Gtk.ComboBoxText()
        self.macro_combo.connect("changed", self.on_macro_chosen)
        self.macro_name = Gtk.Entry(placeholder_text="name")
        self.macro_steps = Gtk.TextView(monospace=True, wrap_mode=Gtk.WrapMode.NONE)
        self.macro_steps.set_size_request(-1, 120)
        steps_scroll = Gtk.ScrolledWindow(hexpand=True)
        steps_scroll.add(self.macro_steps)
        hint = Gtk.Label(xalign=0, label="One step per line: ctrl+c · enter · wait:100 · text:hello · "
                                          "down:shift / up:shift")
        self.macro_record = Gtk.ToggleButton(label="⏺ Record")
        self.macro_record.set_tooltip_text("Type on the keyboard to fill in the steps, then click Stop. "
                                           "Shortcuts the desktop itself uses (Alt+Tab, Win) may not get here.")
        self.macro_record.connect("toggled", self.on_macro_record)
        self.macro_pauses = Gtk.CheckButton(label="Keep pauses")
        self.macro_pauses.set_tooltip_text(f"Turn gaps of {M.PAUSE_MIN} ms or more between keys into wait: steps")
        record = Gtk.Box(spacing=6)
        record.pack_start(self.macro_record, False, False, 0)
        record.pack_start(self.macro_pauses, False, False, 0)
        hint.get_style_context().add_class("dim-label")
        self.macro_text_layout = Gtk.ComboBoxText(halign=Gtk.Align.START)
        for lid, text in M.LAYOUTS.items():
            self.macro_text_layout.append(lid, text)
        self.macro_text_layout.set_active_id(M.detect_layout())
        self.macro_text_layout.set_tooltip_text("Keyboard layout of this computer: text steps are "
                                                "typed with the keys that give those characters there")
        self.macro_layer = Gtk.ComboBoxText()
        self.macro_layer.append("0", "Base layer")
        self.macro_layer.append("1", "Fn layer")
        self.macro_layer.set_active_id("0")
        self.macro_repeat = Gtk.ComboBoxText()
        for mid, text in ((M.REPEAT_TIMES, "Run N times"), (M.REPEAT_HOLD, "Repeat while held"),
                          (M.REPEAT_UNTIL_KEY, "Repeat until a key is pressed")):
            self.macro_repeat.append(str(mid), text)
        self.macro_repeat.set_active_id(str(M.REPEAT_TIMES))
        self.macro_count = Gtk.SpinButton.new_with_range(1, 255, 1)
        repeat = Gtk.Box(spacing=6)
        repeat.pack_start(self.macro_repeat, False, False, 0)
        repeat.pack_start(self.macro_count, False, False, 0)
        save = Gtk.Button(label="Save macro")
        save.get_style_context().add_class("suggested-action")
        save.connect("clicked", self.on_macro_save)
        assign = Gtk.Button(label="Assign to selected key")
        assign.connect("clicked", self.on_macro_assign)
        delete = Gtk.Button(label="Delete macro")
        delete.get_style_context().add_class("destructive-action")
        delete.connect("clicked", self.on_macro_delete)
        buttons = Gtk.Box(spacing=6)
        for b in (save, assign, delete):
            buttons.pack_start(b, False, False, 0)
        rows = [("Macro", self.macro_combo), ("Name", self.macro_name), ("Steps", steps_scroll),
                ("", hint), ("", record), ("Text layout", self.macro_text_layout), ("Layer", self.macro_layer), ("Repeat", repeat), ("", buttons)]
        for r, (text, w) in enumerate(rows):
            g.attach(self._label(text), 0, r, 1, 1)
            g.attach(w, 1, r, 1, 1)
        return g

    def _page_backup(self):
        box = Gtk.Box(spacing=8, margin=16, valign=Gtk.Align.START)
        for text, cb in (("Back up to folder…", self.on_backup),
                         ("Restore from folder…", self.on_restore),
                         ("Restore original settings", self.on_restore_original)):
            b = Gtk.Button(label=text)
            b.connect("clicked", cb)
            box.pack_start(b, False, False, 0)
        return box

    # ---------------------------------------------------------- loading
    def load(self):
        self.say("Reading keyboard…")

        def job(kb):
            return (kb.mode, kb.get_led(), kb.get_custom(), kb.get_battery(),
                    M.parse_store(kb.get_macro_store()), kb.get_palette())

        self.worker.submit(job, self.loaded)

    def loaded(self, result):
        mode, led, custom, battery, macros, palette = result
        self.led = led
        self.palette = palette
        self.fill_macros(macros)
        self.view.colors = P.colors_from_custom(custom)
        self.view.queue_draw()
        bat = f" · Battery {battery}%" if battery is not None else ""
        self.header.set_subtitle(f"{mode}{bat}")
        self.fill_widgets()
        self.say("Ready")

    def fill_widgets(self):
        led = self.led
        self.updating = True
        if not self.effect_combo.set_active_id(str(led.effect)):
            self.effect_combo.append(str(led.effect), f"hw{led.effect}  ({led.effect})")
            self.effect_combo.set_active_id(str(led.effect))
        e = P.EFFECT_BY_HW.get(led.effect)
        has_slot = 1 <= led.effect <= P.LED_SLOTS
        if has_slot:
            s = led.slot(led.effect)
            self.bright.set_value(s.brightness)
            self.speed.set_value(s.speed)
            self.color_combo.set_active_id(str(s.color))
        self.bright.set_sensitive(has_slot)
        self.speed.set_sensitive(has_slot and (e is None or e.speed))
        self.color_combo.set_sensitive(has_slot and (e is None or e.color))
        rgb = self._effect_rgb()
        self.color_rgb.set_sensitive(rgb is not None)
        self.color_reset.set_sensitive(rgb is not None)
        if rgb is not None:
            self.color_rgb.set_rgba(Gdk.RGBA(*(c / 255 for c in rgb), 1.0))
        self.side_combo.set_active_id(str(led.side_mode))
        self.knob_combo.set_active_id(str(led.knob_mode))
        self.os_combo.set_active_id(str(led.os_mode))
        self.winlock.set_active(led.win_lock)
        self.sleep_combo.remove_all()
        for sec in sorted({*P.SLEEP_CHOICES, led.sleep} - {0}) + [0]:
            self.sleep_combo.append(str(sec), P.sleep_text(sec))
        self.sleep_combo.set_active_id(str(led.sleep))
        self.updating = False
        self.update_readout()
        self.tick()

    def update_readout(self):
        if self.led is not None:
            left, right = readout(self.led, len(self.view.selected), self.palette)
            self.readout_left.set_text(left)
            self.readout_right.set_text(right)

    def tick(self):
        """Redraw the effect preview; runs every 50 ms."""
        if self.led is not None:
            animated = A.is_animated(self.led)
            if animated or self.view.preview is not None or self.led.effect == 1:
                motion = Gtk.Settings.get_default().get_property("gtk-enable-animations")
                t = (GLib.get_monotonic_time() - self.t0) / 1e6 if motion else 1.0
                self.view.preview = A.frame(self.led, t, self.palette)
                self.view.queue_draw()
        return True

    # ---------------------------------------------------------- lighting
    def on_led_widget(self, *_args):
        if self.updating or self.led is None:
            return
        led = self.led
        hw = int(self.effect_combo.get_active_id())
        effect_changed = hw != led.effect
        led.effect = hw
        if 1 <= hw <= P.LED_SLOTS:
            if effect_changed:  # show the stored settings of the newly chosen effect
                self.fill_widgets()
            else:
                led.set_slot(hw, P.EffectSlot(int(self.bright.get_value()),
                                              int(self.speed.get_value()),
                                              int(self.color_combo.get_active_id())))
        led.side_mode = int(self.side_combo.get_active_id())
        led.knob_mode = int(self.knob_combo.get_active_id())
        led.os_mode = int(self.os_combo.get_active_id())
        led.win_lock = self.winlock.get_active()
        led.sleep = int(self.sleep_combo.get_active_id())
        self.fill_widgets()
        self.send_led()

    def _effect_rgb(self):
        """The actual color the current effect shows, if it has a single one."""
        led, e = self.led, P.EFFECT_BY_HW.get(self.led.effect)
        if self.palette is None or e is None or not e.color or led.effect >= P.PALETTE_COUNT:
            return None
        color = led.slot(led.effect).color
        return P.palette_color(self.palette, led.effect, color) if color < P.PALETTE_COLORS else None

    def on_effect_rgb(self, button):
        led = self.led
        c = button.get_rgba()
        rgb = (round(c.red * 255), round(c.green * 255), round(c.blue * 255))
        color = led.slot(led.effect).color
        self.palette = P.set_palette_color(self.palette, led.effect, color, rgb)
        self.send_palette(f"{P.EFFECT_BY_HW[led.effect].name}: {P.COLORS[color]} → {P.rgb_hex(rgb)}")

    def on_effect_colors_reset(self, _b):
        hw = self.led.effect
        self.palette = P.reset_palette(self.palette, hw)
        self.send_palette(f"{P.EFFECT_BY_HW[hw].name}: factory colors")

    def send_palette(self, message):
        raw = self.palette
        self.fill_widgets()
        self.worker.submit(lambda kb: kb.set_palette(raw), lambda _r: self.say(message), key="palette")

    def send_led(self):
        raw = self.led.to_bytes()
        self.worker.submit(lambda kb: kb.set_led(P.LedConfig(raw)),
                           lambda _r: self.say("Saved to keyboard"), key="led")

    def ensure_custom_effect(self):
        if self.led.effect != CUSTOM_HW:
            self.led.effect = CUSTOM_HW
            self.fill_widgets()
            self.send_led()

    def send_custom(self, message):
        raw = P.custom_from_colors(self.view.colors)
        self.worker.submit(lambda kb: kb.set_custom(raw), lambda _r: self.say(message), key="custom")

    def paint_selection(self, rgb):
        if self.led is None:
            return
        if not self.view.selected:
            self.say("Select keys on the board first (Ctrl+click adds more)")
            return
        for idx in self.view.selected:
            self.view.colors[idx] = rgb
        self.view.queue_draw()
        self.ensure_custom_effect()
        self.send_custom(f"Colored {len(self.view.selected)} key(s)")

    def on_color_picked(self, _button):
        dlg = Gtk.ColorChooserDialog(title="Paint selected keys", transient_for=self)
        dlg.set_use_alpha(False)
        if dlg.run() == Gtk.ResponseType.OK:
            c = dlg.get_rgba()
            self.paint_selection((round(c.red * 255), round(c.green * 255), round(c.blue * 255)))
        dlg.destroy()

    def on_select_all(self, _b):
        self.view.selected = {idx for idx, *_ in K.KEYS if idx != K.BY_NAME["knob"]}
        self.view.queue_draw()
        self.on_selection()

    def load_preset(self, preset):
        if self.led is None:
            return
        self.view.colors.update(T.render(preset))
        self.view.queue_draw()
        self.ensure_custom_effect()
        self.send_custom(f"Theme: {preset.name}")

    # ------------------------------------------------------------- remap
    def on_clear_selection(self, _b):
        self.view.selected.clear()
        self.view.queue_draw()
        self.on_selection()

    def on_selection(self):
        self.update_readout()
        sel = self.view.selected
        if len(sel) == 1:
            idx = next(iter(sel))
            self.remap_key.set_text(f"{K.BY_INDEX.get(idx, idx)}  (#{idx})")
            self.show_mapping()
        else:
            self.remap_key.set_text("Click a single key" if sel else "Click a key on the drawing above")
            self.remap_current.set_text("–")

    def _selected_key(self):
        return next(iter(self.view.selected)) if len(self.view.selected) == 1 else None

    def show_mapping(self):
        idx = self._selected_key()
        if idx is None:
            return
        layer = int(self.remap_layer.get_active_id())
        self.worker.submit(lambda kb: P.matrix_entry(kb.get_matrix(layer), idx),
                           lambda e: self.remap_current.set_text(describe_entry(e)), key="show")

    def _write_entry(self, idx, layer, entry, message):
        def job(kb):
            raw = kb.get_matrix(layer)
            kb.set_matrix(P.set_matrix_entry(raw, idx, entry), layer)
            check = P.matrix_entry(kb.get_matrix(layer), idx)
            if check != entry:
                raise AulaError(f"verification failed: read back {check.hex()}")
            return check

        def done(e):
            self.remap_current.set_text(describe_entry(e))
            self.say(message)

        self.worker.submit(job, done)

    def on_remap(self, _b):
        idx, target = self._selected_key(), self.remap_target.get_active_id()
        if idx is None or target is None:
            self.say("Pick one key on the drawing and a new function")
            return
        if target in K.MODIFIERS:
            entry = P.key_entry(modifiers=K.MODIFIERS[target])
        elif target == "none":
            entry = P.key_entry()
        else:
            entry = P.key_entry(hid=K.HID[target])
        layer = int(self.remap_layer.get_active_id())
        self._write_entry(idx, layer, entry, f"{K.BY_INDEX.get(idx, idx)} → {target}")

    def on_remap_restore(self, _b):
        idx = self._selected_key()
        if idx is None:
            self.say("Pick one key on the drawing")
            return
        layer = int(self.remap_layer.get_active_id())
        fname = "cmd_41.hex" if layer == 0 else f"cmd_41_layer{layer}.hex"
        path = os.path.join(ORIGINAL_BACKUP, fname)
        if not os.path.exists(path):
            self.say("Factory keymap isn't available in this install (the backup/ folder is missing)")
            return
        with open(path) as f:
            entry = P.matrix_entry(bytes.fromhex(f.read().strip()), idx)
        self._write_entry(idx, layer, entry, f"{K.BY_INDEX.get(idx, idx)} restored")

    # ------------------------------------------------------------ macros
    NEW_MACRO = "__new__"

    def fill_macros(self, macros, select=None):
        self.macro_list = macros
        self.updating = True
        self.macro_combo.remove_all()
        self.macro_combo.append(self.NEW_MACRO, "New macro…")
        for i, m in enumerate(macros):
            self.macro_combo.append(str(i), m.name)
        self.updating = False
        self.macro_combo.set_active_id(str(select) if select is not None else self.NEW_MACRO)

    def on_macro_chosen(self, _c):
        if self.updating:
            return
        mid = self.macro_combo.get_active_id()
        buf = self.macro_steps.get_buffer()
        if mid in (None, self.NEW_MACRO):
            self.macro_name.set_text("")
            buf.set_text("")
            return
        m = self.macro_list[int(mid)]
        self.macro_name.set_text(m.name)
        buf.set_text("# stored events (comment lines are ignored); type new steps below to replace them\n"
                     + "\n".join(f"# {e.describe()}" for e in m.events) + "\n")

    def _macro_steps(self):
        buf = self.macro_steps.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]

    def on_macro_save(self, _b):
        name = self.macro_name.get_text().strip()
        if not name:
            self.say("Give the macro a name")
            return
        try:
            events = M.parse_steps(self._macro_steps(), layout=self.macro_text_layout.get_active_id())
        except ValueError as e:
            self.say(f"Steps: {e}")
            return
        macros = list(self.macro_list)
        index = next((i for i, m in enumerate(macros) if m.name == name), None)
        if index is None:
            macros.append(M.Macro(name, events))
            index = len(macros) - 1
        else:
            macros[index] = M.Macro(name, events)
        store = M.build_store(macros)
        self.worker.submit(lambda kb: kb.set_macro_store(store),
                           lambda _r: (self.fill_macros(macros, index), self.say(f"Saved macro {name!r}")))

    def on_macro_assign(self, _b):
        mid = self.macro_combo.get_active_id()
        idx = self._selected_key()
        if mid in (None, self.NEW_MACRO):
            self.say("Save the macro first, then assign it")
            return
        if idx is None:
            self.say("Select one key on the board to assign the macro to")
            return
        mode = int(self.macro_repeat.get_active_id())
        entry = M.macro_entry(int(mid), mode, int(self.macro_count.get_value()))
        layer = int(self.macro_layer.get_active_id())
        name = self.macro_list[int(mid)].name
        self._write_entry(idx, layer, entry, f"{name} → {'Fn+' if layer else ''}{K.BY_INDEX.get(idx, idx)}")

    def on_macro_record(self, button):
        if button.get_active():
            self.recording, self.rec_held, self.rec_skipped = [], set(), 0
            button.set_label("⏹ Stop")
            self.say("Recording: type the macro on the keyboard, then click Stop")
            return
        rec, self.recording = self.recording or [], None
        button.set_label("⏺ Record")
        end = rec[-1][2] if rec else 0
        rec += [(name, False, end) for name in sorted(self.rec_held)]  # still held at Stop
        layout = self.macro_text_layout.get_active_id()
        steps = M.steps_from_recording(rec, layout, self.macro_pauses.get_active())
        if not steps:
            self.say("Nothing was recorded")
            return
        self.macro_steps.get_buffer().set_text("\n".join(steps) + "\n")
        skipped = f" ({self.rec_skipped} key(s) without a name skipped)" if self.rec_skipped else ""
        self.say(f"Recorded {sum(d for _n, d, _t in rec)} key press(es){skipped}. "
                 "Check the steps, then Save macro")

    def on_record_key(self, _w, event):
        if self.recording is None:
            return False
        name = backends.key_name(event)
        down = event.type == Gdk.EventType.KEY_PRESS
        if name is None:
            self.rec_skipped += down
        elif down and name not in self.rec_held:  # auto-repeat sends more presses
            self.rec_held.add(name)
            self.recording.append((name, True, event.time))
        elif not down and name in self.rec_held:  # keys held before Record are ignored
            self.rec_held.discard(name)
            self.recording.append((name, False, event.time))
        return True  # keys go to the recording, not to the widgets

    def on_macro_delete(self, _b):
        mid = self.macro_combo.get_active_id()
        if mid in (None, self.NEW_MACRO):
            return
        index = int(mid)
        name = self.macro_list[index].name
        if not self._confirm(f"Delete macro {name!r}? Keys using it get their factory function back."):
            return
        current = list(self.macro_list)

        def job(kb):
            return delete_macro(kb, current, index)

        self.worker.submit(job, lambda left: (self.fill_macros(left), self.say(f"Deleted macro {name!r}")))

    # ------------------------------------------------------------ backup
    def _pick_folder(self, title):
        dlg = Gtk.FileChooserDialog(title=title, parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK)
        folder = dlg.get_filename() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        return folder

    def _confirm(self, text):
        dlg = Gtk.MessageDialog(transient_for=self, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.OK_CANCEL, text=text)
        ok = dlg.run() == Gtk.ResponseType.OK
        dlg.destroy()
        return ok

    def on_backup(self, _b):
        folder = self._pick_folder("Back up keyboard settings to…")
        if not folder:
            return

        def job(kb):
            for fname, get, _ in BACKUP:
                with open(os.path.join(folder, fname), "w") as f:
                    f.write(get(kb).hex())

        self.say("Backing up…")
        self.worker.submit(job, lambda _r: self.say(f"Backed up to {folder}"))

    def _restore(self, folder):
        def job(kb):
            for fname, _, put in BACKUP:
                path = os.path.join(folder, fname)
                if os.path.exists(path):
                    with open(path) as f:
                        put(kb, bytes.fromhex(f.read().strip()))

        self.say("Restoring…")
        self.worker.submit(job, lambda _r: (self.say("Restored"), self.load()))

    def on_restore(self, _b):
        folder = self._pick_folder("Restore keyboard settings from…")
        if folder and self._confirm(f"Overwrite the keyboard's settings with the backup in\n{folder}?"):
            self._restore(folder)

    def on_restore_original(self, _b):
        if not os.path.isdir(ORIGINAL_BACKUP):
            self.say("Factory settings aren't available in this install (the backup/ folder is missing)")
            return
        if self._confirm("Put back the factory settings of a stock AULA F75 (lighting, per-key colors, keymap)?"):
            self._restore(ORIGINAL_BACKUP)

    # ------------------------------------------------------------ status
    def say(self, text):
        self.status.set_text(text)

    def show_error(self, text):
        self.say(f"Error: {text}")
        self.header.set_subtitle("not connected – press reload")


def main() -> int:
    win = AulaWindow()
    win.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
