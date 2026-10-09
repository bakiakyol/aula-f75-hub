"""GTK 3 interface for the AULA F75 configuration tool.

Start with:  ./aula.sh gui   (or python3 -m aula gui)
"""

import os
import queue
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import keymap as K  # noqa: E402
from . import presets as T  # noqa: E402
from . import protocol as P  # noqa: E402
from .cli import BACKUP  # noqa: E402
from .device import AulaError, Keyboard  # noqa: E402

CUSTOM_HW = P.EFFECT_BY_NAME["custom"].hw
KNOB_RECT = (605, 30, 630, 57)  # drawn top right, next to F12
ORIGINAL_BACKUP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup")

SWATCHES = [
    ("Red", (255, 0, 0)), ("Orange", (255, 80, 0)), ("Yellow", (255, 200, 0)),
    ("Green", (0, 255, 0)), ("Cyan", (0, 213, 255)), ("Blue", (0, 0, 255)),
    ("Purple", (96, 0, 255)), ("Pink", (255, 0, 144)), ("White", (255, 255, 255)),
    ("Off", (0, 0, 0)),
]


# Colors 0-6 as stored in the keyboard's palette (command 0x49)
PALETTE = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
           (255, 0, 255), (0, 255, 255), (255, 255, 255)]
# Ends on violet, not magenta: a magenta right edge reads as "red again" next to blue.
RAINBOW = T.Preset("rainbow", "", [(0.0, (255, 0, 0)), (0.17, (255, 128, 0)), (0.33, (255, 230, 0)),
                                   (0.5, (0, 255, 0)), (0.67, (0, 220, 255)), (0.83, (0, 60, 255)),
                                   (1.0, (140, 0, 255))])


def effect_preview(led: P.LedConfig) -> tuple[dict[int, tuple] | None, str]:
    """Static approximation of the running effect for the drawing, plus a caption."""
    hw = led.effect
    e = P.EFFECT_BY_HW.get(hw)
    name = e.name if e else f"effect {hw}"
    if hw == CUSTOM_HW:
        return None, "Showing your custom key colors"
    if not 1 <= hw <= P.LED_SLOTS:
        return {}, f"{name}: no preview"
    slot = led.slot(hw)
    if e is not None and e.color and slot.color < len(PALETTE):
        colors = {idx: PALETTE[slot.color] for idx, *_ in K.KEYS}
    else:
        colors = T.render(RAINBOW)
    k = max(0.15, slot.brightness / 9)
    colors = {i: tuple(round(v * k) for v in c) for i, c in colors.items()}
    moving = "" if hw == 1 else " (animated on the keyboard)"
    return colors, f"Preview: {name}{moving} – coloring keys switches to custom"


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
            except (AulaError, OSError, ValueError) as e:
                if self.kb is not None:
                    try:
                        self.kb.close()
                    except OSError:
                        pass
                self.kb = None
                GLib.idle_add(_once, self.on_error, str(e))
                continue
            if done:
                GLib.idle_add(_once, done, result)


class KeyboardView(Gtk.DrawingArea):
    """Drawing of the board; click to select keys (Ctrl/Shift-click adds)."""

    MARGIN = 12

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
        cr.set_source_rgb(0.12, 0.12, 0.14)
        self._rounded(cr, ox + 22 * s, oy + 22 * s, 616 * s, 249 * s, 10 * s)
        cr.fill()
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription(f"Sans Bold {max(6.5, 7.0 * s):.1f}")
        layout.set_font_description(font)
        for idx, _name, label, rect in K.KEYS:
            x1, y1, x2, y2 = _key_rect(idx, rect)
            x, y, w, h = ox + x1 * s, oy + y1 * s, (x2 - x1) * s, (y2 - y1) * s
            shown = self.preview if self.preview is not None else self.colors
            r, g, b = shown.get(idx, (40, 40, 40))
            cr.new_path()
            if idx == K.BY_NAME["knob"]:
                cr.arc(x + w / 2, y + h / 2, w / 2, 0, 6.2832)
            else:
                self._rounded(cr, x, y, w, h, 4 * s)
            cr.set_source_rgb(r / 255, g / 255, b / 255)
            cr.fill_preserve()
            if idx in self.selected:
                cr.set_source_rgb(1, 1, 1)
                cr.set_line_width(3 * s)
            else:
                cr.set_source_rgb(0, 0, 0)
                cr.set_line_width(1)
            cr.stroke()
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            cr.set_source_rgb(*((0, 0, 0) if lum > 140 else (1, 1, 1)))
            layout.set_text(label, -1)
            tw, th = layout.get_pixel_size()
            cr.move_to(x + (w - tw) / 2, y + (h - th) / 2)
            PangoCairo.show_layout(cr, layout)

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
        self.updating = False  # True while widgets are filled from device state
        self.worker = Worker(self.show_error)

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

        self.view = KeyboardView(self.on_selection)
        root.pack_start(self.view, True, True, 0)
        root.pack_start(self._color_bar(), False, False, 0)
        root.pack_start(Gtk.Separator(), False, False, 0)

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        stack.add_titled(self._page_lighting(), "lighting", "Lighting")
        stack.add_titled(self._page_remap(), "remap", "Key remap")
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

    def _color_bar(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin=8)
        self.caption = Gtk.Label(xalign=0.5)
        self.caption.get_style_context().add_class("dim-label")
        outer.pack_start(self.caption, False, False, 0)
        box = Gtk.Box(spacing=6)
        outer.pack_start(box, False, False, 0)
        box.pack_start(Gtk.Label(label="Selected keys:"), False, False, 0)
        for name, rgb in SWATCHES:
            btn = Gtk.Button()
            btn.set_tooltip_text(name)
            area = Gtk.DrawingArea()
            area.set_size_request(22, 16)
            area.connect("draw", lambda _w, cr, c=rgb: (cr.set_source_rgb(*(v / 255 for v in c)), cr.paint()))
            btn.add(area)
            btn.connect("clicked", lambda _b, c=rgb: self.paint_selection(c))
            box.pack_start(btn, False, False, 0)
        picker = Gtk.ColorButton()
        picker.set_tooltip_text("Custom color")
        picker.connect("color-set", self.on_color_picked)
        box.pack_start(picker, False, False, 0)
        sel_all = Gtk.Button(label="Select all")
        sel_all.connect("clicked", self.on_select_all)
        box.pack_end(sel_all, False, False, 0)
        return outer

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
        self.bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 9, 1)
        self.speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 4, 1)
        for sc in (self.bright, self.speed):
            sc.set_digits(0)
            sc.set_hexpand(True)
            sc.connect("value-changed", self.on_led_widget)
        rows = [("Effect", self.effect_combo), ("Color", self.color_combo),
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
        self.winlock = Gtk.Switch(halign=Gtk.Align.START)
        self.winlock.connect("notify::active", self.on_led_widget)
        rows = [("Side light", self.side_combo), ("Knob", self.knob_combo),
                ("OS mode", self.os_combo), ("Windows key lock", self.winlock)]
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
            return (kb.mode, kb.get_led(), kb.get_custom(), kb.get_battery())

        self.worker.submit(job, self.loaded)

    def loaded(self, result):
        mode, led, custom, battery = result
        self.led = led
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
        self.side_combo.set_active_id(str(led.side_mode))
        self.knob_combo.set_active_id(str(led.knob_mode))
        self.os_combo.set_active_id(str(led.os_mode))
        self.winlock.set_active(led.win_lock)
        self.updating = False
        self.view.preview, caption = effect_preview(led)
        self.caption.set_text(caption)
        self.view.queue_draw()

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
        self.fill_widgets()
        self.send_led()

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
            self.say("Select keys on the drawing first (Ctrl+click to pick several)")
            return
        for idx in self.view.selected:
            self.view.colors[idx] = rgb
        self.view.queue_draw()
        self.ensure_custom_effect()
        self.send_custom(f"Colored {len(self.view.selected)} key(s)")

    def on_color_picked(self, button):
        c = button.get_rgba()
        self.paint_selection((round(c.red * 255), round(c.green * 255), round(c.blue * 255)))

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
    def on_selection(self):
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
        with open(os.path.join(ORIGINAL_BACKUP, fname)) as f:
            entry = P.matrix_entry(bytes.fromhex(f.read().strip()), idx)
        self._write_entry(idx, layer, entry, f"{K.BY_INDEX.get(idx, idx)} restored")

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
        if self._confirm("Put back the settings the keyboard had before this tool was first used?"):
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
