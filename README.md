<div align="center">

# aula-f75-hub

**Lighting, per-key RGB and key remapping for the AULA F75 keyboard. On Linux, without the vendor software.**

**English** · [Türkçe](README.tr.md)

[![tests](https://github.com/bakiakyol/aula-f75-hub/actions/workflows/tests.yml/badge.svg)](https://github.com/bakiakyol/aula-f75-hub/actions/workflows/tests.yml)
![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![platform](https://img.shields.io/badge/platform-Linux-informational)

<img src="docs/screenshots/main.png" alt="Main window: the board drawn in its real key colors, three keys selected for painting" width="820">

</div>

The official AULA software only runs on Windows, and on the machine it was tried on,
its lighting settings did not even work there. This project talks to the keyboard
directly over its HID configuration channel. The protocol was worked out by reading
the official app's code (without running it) and checking every finding on a real
keyboard.

## Features

- **15 lighting effects** with color, brightness and speed: breathing, raindrops,
  snake, waterfall, rainbow wheel, reactive ripples… Single-color effects can use
  **any RGB color**, not just the 7 built-in ones.
- **Per-key RGB**: click keys on the drawing and paint them. Includes 9 ready-made themes.
- **Key remapping** on the base and Fn layers, each change read back and verified.
- **Macros**: key combos, typed text and delays, run once, N times, while held or
  until another key is pressed. Write the steps or record them from the keyboard.
  Text follows your keyboard layout (US or Turkish Q).
- **Device settings**: side light, knob mode (volume or lighting), OS mode
  (Windows / Android / Mac), Windows key lock, sleep timer.
- **Battery level** (experimental) and connection type in the header.
- **Backup and restore**, including the keyboard's factory settings.
- **Animated previews** that show roughly what the running effect looks like.
- A full **command-line tool** for scripting, plus a GTK 3 interface.
- No dependencies beyond Python. The GUI uses GTK 3, which ships with most desktops.

<table>
<tr>
<td><img src="docs/screenshots/rainbow.png" alt="Rainbow wheel effect previewed on the drawing" width="400"></td>
<td><img src="docs/screenshots/remap.png" alt="Key remap page with Caps Lock selected" width="400"></td>
</tr>
<tr>
<td align="center">Animated effect preview</td>
<td align="center">Key remapping</td>
</tr>
</table>

## Supported hardware

The connection type is chosen with the switch on the back of the keyboard
(2.4G / wired / Bluetooth). The tool finds whichever one is active.

| Keyboard | Connection | Status |
|---|---|---|
| AULA F75 | 2.4G dongle (`3554:fa09`) | ✅ Verified |
| AULA F75 | Bluetooth (`3554:fa07`) | ✅ Verified |
| AULA F75 | Cable (`258a:010c`) | ❌ Not supported yet (different transport) |
| Other AULA models | – | ❓ Unknown. Please [report](../../issues/new/choose) |

## Installation

```bash
git clone https://github.com/bakiakyol/aula-f75-hub.git
cd aula-f75-hub
./install.sh
```

`install.sh` installs a udev rule so the keyboard can be used without `sudo`, puts an
`aula` command in `~/.local/bin` and adds **AULA F75** to the application menu.
`./install.sh --remove` undoes all of it.

The GUI needs GTK 3 for Python, which Linux Mint and Ubuntu already include. On other
distributions install `python3-gi` and `gir1.2-gtk-3.0` (or your distro's equivalent).
The command-line tool needs nothing but Python 3.10+.

## Usage

### Graphical interface

```bash
aula gui
```

Click a key to select it (**Ctrl+click** adds more), then pick a color below the
board. On the Lighting page, the color button next to **Color** gives the running
effect any color you like; **Factory colors** undoes it. The pages on the left change the effect, remap keys, adjust the side light,
knob and OS mode, and make backups.

### Command line

```bash
aula info                                  # effect, brightness, battery, side light, knob…
aula effects                               # list effects and colors
aula effect breathing -c blue -b 9 -s 2    # -c color, -b brightness 0-9, -s speed 0-4
aula effect breathing --rgb ff6000         # any color for this effect (replaces the chosen one)
aula palette                               # colors of every effect; --reset puts the factory ones back
aula key-color --clear all=0010ff w=ff0000 a=ff0000 s=ff0000 d=ff0000
aula preset synthwave                      # built-in per-key theme
aula remap capslock lctrl                  # undo: aula remap capslock capslock
aula remap f1 esc -l 1                     # remap on the Fn layer
aula macro set hello "text:hello" --key y -l 1          # Fn+Y types "hello"
aula macro set paste "ctrl+c" "wait:100" "ctrl+v" --key f1 --repeat 2
aula macro list                            # stored macros and their keys
aula macro delete hello                    # its key gets its factory function back
aula side-light breathing                  # off | fill | breathing | static
aula knob lighting                         # media | lighting
aula os mac                                # windows | android | mac
aula win-lock on
aula sleep 10m                             # sleep after 10 idle minutes (30 s steps up to 20m, or off)
aula backup ~/aula-backup
aula restore ~/aula-backup
```

On a Turkish Q layout the letters `ğ ü ş ö ç ı` work as key names too.

### Themes

`aula preset NAME` paints every key at once (or pick one on the Lighting page of the
GUI). `aula preset` on its own lists them.

| Theme | Colors |
|---|---|
| `synthwave` | purple → pink → cyan, white WASD/arrows, orange Esc |
| `cyberpunk` | neon yellow → hot pink → cyan, white WASD/arrows, red Esc |
| `dracula` | deep purple → pink → cyan, yellow WASD, green Esc |
| `matrix` | dark green → bright green → dark green, red Esc |
| `sunset` | deep purple → orange → yellow, white WASD |
| `volcano` | dark red → bright orange → yellow, cyan WASD/Esc |
| `aurora` | deep blue → aurora green → purple, hot pink WASD |
| `miami-vice` | bright cyan → hot pink → purple, yellow WASD |
| `toxic` | dark grey → acid green → dark grey, purple WASD |

### Macros

A macro is a list of steps that the keyboard plays back by itself when you press a
key. It is stored on the keyboard, so it keeps working in every program, after a
restart, and on other computers.

**In the GUI**, open the **Macros** page:

1. Choose **New macro…**, type a name and write the steps, one per line.
2. Press **Save macro**.
3. Click the key that should run it on the drawing, pick the layer (**Fn layer**
   means Fn + that key) and how often it repeats.
4. Press **Assign to selected key**.

Instead of writing the steps you can **record** them: press **⏺ Record**, type on
the keyboard, then click **⏹ Stop**. The keys become steps (typed characters turn into
`text:` steps, shortcuts into combos like `ctrl+a`) that you can check and edit before
saving. Tick **Keep pauses** to keep gaps of 100 ms or more as `wait:` steps. Type the
name first: while recording, every key goes to the recording. Shortcuts the desktop
itself catches (Alt+Tab, the Win key) and keys without a name here (volume, the knob)
are not recorded.

Choosing a stored macro shows its events as comment lines. To change it, write new
steps below them and save it under the same name.

**On the command line**, `aula macro set` saves a macro and, with `--key`, assigns it:

```bash
aula macro set NAME STEP [STEP …] [--key KEY] [-l LAYER] [--repeat N | --while-held | --until-key]
aula macro assign KEY NAME [-l LAYER]      # assign a stored macro to another key
```

#### Steps

| Step | What it does | Examples |
|---|---|---|
| `text:…` | types the text | `text:Hello, world!` |
| a key or a combo | presses the keys together, then lets go | `enter` · `f5` · `ctrl+c` · `ctrl+shift+t` · `alt+tab` · `win` |
| `wait:MS` | waits MS milliseconds before the next step (not as the first step) | `wait:500` |
| `down:KEY` / `up:KEY` | presses or releases one key, for keys that stay held across other steps | `down:shift` · `up:shift` |

- **Key names:** `a`–`z`, `0`–`9`, `f1`–`f12`, `enter`, `esc`, `tab`, `space`,
  `backspace`, `delete`, `insert`, `home`, `end`, `pgup`, `pgdn`, `up`, `down`,
  `left`, `right`, `printscreen`, `capslock`, `menu` and the symbol keys (`minus`,
  `comma`, `slash`…). `aula keys` lists them all at the end.
- **Modifiers:** `ctrl`, `shift`, `alt`, `win` (or `super`), `altgr`. For one side
  only: `lctrl`, `rctrl`, `lshift`, `rshift`, `lalt`, `ralt`, `lwin`, `rwin`.
- Events are 20 ms apart. Use `wait:` for a longer pause after a step, or `--delay MS`
  to change the spacing of a whole macro.
- Mouse buttons and media keys (volume, play) can't be used in steps yet.

#### Text and keyboard layouts

The keyboard only sends key positions; the computer's layout decides which character
each one gives. So `text:` steps are typed with the keys that give those characters
on **your** layout, which is detected automatically (`setxkbmap`, then
`/etc/default/keyboard`).

| Layout | What `text:` can type |
|---|---|
| `us` (English US) | ASCII: letters, digits, space, punctuation, Enter (`\n`), Tab |
| `tr` (Turkish Q) | the same plus `ı İ ğ ü ş ö ç Ğ Ü Ş Ö Ç` and the AltGr characters `@ € ₺ { } [ ] \ \| ~ < >` |

To override the detected layout, use `--layout us` or `--layout tr`, or the
**Text layout** box in the GUI. A macro is typed for the layout it was saved with, so
on a computer with a different layout its text comes out differently. On other layouts,
use `us` and stick to letters and digits that sit in the same place as on a US
keyboard.

#### Repeat modes

| GUI | Command line | Behavior |
|---|---|---|
| Run N times | `--repeat N` (default 1) | plays the macro N times (1-255) |
| Repeat while held | `--while-held` | repeats as long as the key is held down |
| Repeat until a key is pressed | `--until-key` | keeps repeating until you press any key |

#### Memory

All macros share **512 bytes** on the keyboard, including the factory macro `M1`.

- Every key press costs 8 bytes; a character that needs Shift or AltGr costs 16.
- Each macro also takes 5 bytes plus 2 per letter of its name (at most 30 letters).

That is room for about 55 lowercase letters of text in total. Macros are meant for
shortcuts and short phrases, not long paragraphs. When a macro doesn't fit, saving it
fails with a message and nothing on the keyboard changes.

#### Deleting

`aula macro delete NAME` (or **Delete macro** in the GUI) removes a macro. Keys that
ran it get their factory function back.

#### Examples

```bash
# Fn+F1 opens Firefox from the app menu
aula macro set firefox "win" "wait:400" "text:firefox" "wait:300" "enter" --key f1 -l 1

# Fn+S types a signature on two lines
aula macro set sig "text:Best regards," "enter" "text:Alex" --key s -l 1

# Fn+D duplicates the current line in many editors: Home, Shift+End, copy, End, Enter, paste
aula macro set dup "home" "shift+end" "ctrl+c" "end" "enter" "ctrl+v" --key d -l 1

# For games: hold Fn+Space to keep pressing Space
aula macro set spam "space" --key space -l 1 --while-held

# Keep W held while jumping, then let go
aula macro set runjump "down:w" "wait:200" "space" "wait:300" "up:w" --key w -l 1
```

### Lighting effects

| # | Effect | # | Effect |
|---|---|---|---|
| 1 | static | 10 | snake |
| 2 | breathing | 11 | stream |
| 3 | spectrum | 12 | reactive (pressed key lights up) |
| 4 | ripple-row | 13 | center-wave |
| 5 | raindrops | 15 | rainbow-wheel |
| 6 | wave | 16 | waterfall |
| 7 | ripple | 17 | center-flash |
| 8 | twinkle | 32 | custom (per-key colors) |

The official app's effect names and numbers don't match the firmware, so this list
was made by trying every effect number on the keyboard.

## Safety

- `backup/` holds the factory settings of a stock F75, read before this tool ever
  wrote to it. `aula restore backup` puts them on your keyboard.
- Holding **Fn + Esc** factory-resets the keyboard.
- The tool only sends configuration commands it understands. It never touches the
  firmware or the bootloader.

## Troubleshooting

| Message | Fix |
|---|---|
| `permission denied` | Run `./install.sh`, or install the udev rule from `udev/` by hand |
| `the keyboard didn't answer` | The keyboard is asleep. Press any key and try again (`aula sleep` sets how soon it sleeps) |
| `a key seems to be held down` | Let go of the keyboard. The tool waits for all keys to be released before it talks to the keyboard; otherwise a dropped key-release can make a key repeat forever |
| `connected by cable` | Use the 2.4G dongle or Bluetooth; wired mode isn't supported yet |

## How it works

The keyboard listens on a vendor HID channel (report `0x13`, 20-byte packets with an
8-bit checksum) and acknowledges every write by echoing it back. Settings live in a
handful of blocks: a 128-byte lighting block, a 504-byte keymap per layer, and a
378-byte per-key color table. The full write-up is in
[docs/protocol.md](docs/protocol.md).

## Roadmap

- [ ] Wired mode (same data, different transport)
- [x] Bluetooth
- [x] Macros
- [x] Recording macros from the keyboard in the GUI
- [x] More themes

## Contributing

Bug reports and device reports are very welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

This is an independent project. It is not affiliated with, endorsed by, or supported
by AULA. "AULA" is used only to name the hardware it works with. Use at your own risk.

## License

[MIT](LICENSE) © 2026 Baki Akyol
