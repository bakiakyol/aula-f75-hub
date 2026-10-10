# aula-f75-hub on macOS

macOS support uses the same protocol code as Linux. Only finding and opening the
keyboard is different: it goes through [hidapi](https://github.com/trezor/cython-hidapi)
(`pip install hidapi`), which `install-macos.sh` sets up for you.

> Status: new. Please run the [test checklist](#test-checklist) and report what
> happens.

## Installation

You need [Homebrew](https://brew.sh).

```sh
git clone https://github.com/bakiakyol/aula-f75-hub.git
cd aula-f75-hub
./install-macos.sh
```

The script installs Python, GTK 3 and its Python bindings with Homebrew, puts hidapi
in a virtual environment (`.venv` in this folder), and creates:

- `~/.local/bin/aula`: the command-line tool
- `~/Applications/AULA F75.app`: the GUI, also in Launchpad and Spotlight

`./install-macos.sh --no-gui` skips GTK. `./install-macos.sh --remove` undoes it all.
If `aula` isn't found afterwards, add `~/.local/bin` to your PATH as the script
explains, then open a new terminal.

## Permissions

macOS may ask for **Input Monitoring** the first time, because the dongle is a
keyboard. If `aula devices` lists the keyboard but every other command says
"cannot open the keyboard":

1. System Settings > Privacy & Security > **Input Monitoring**
2. Turn on your terminal app (and **AULA F75** if you use the GUI)
3. Quit and reopen the terminal or the app

## Good to know

- **Close the official AULA app** if it runs; only one program can use the
  configuration channel.
- The tool waits until no key is held before it talks to the keyboard (see
  "Troubleshooting" in the README). On macOS it checks this with Quartz
  (`CGEventSourceKeyState`).
- Macro `text:` steps follow the input source:
  - **Turkish Q - PC** → `tr_mac_pc`: like the PC Turkish Q layout, without the
    Option (AltGr) characters
  - Apple's **Turkish Q** → `tr_mac`: letters (with ı İ ğ ü ş ö ç), digits and spaces
  - anything else → `us`

  Characters that a layout can't type are refused when you save the macro, so
  nothing comes out wrong. `--layout` (or "Text layout" in the GUI) overrides it.
- In macros, `win` / `lwin` is the **Command** key and `alt` is **Option**.
- Recording macros in the GUI uses key positions (macOS virtual key codes).
  PrintScreen, Scroll Lock and Pause arrive as F13, F14 and F15.

## Test checklist

Run these in order with the keyboard on the **2.4G dongle** (switch on the back on
2.4G). Write down anything that doesn't match. If a command fails, copy its whole
output. Leave the keyboard alone while a command runs, unless a step says otherwise.

| # | Do | Expected |
|---|---|---|
| 1 | `aula devices` | one line: `2.4G dongle … (supported)` |
| 2 | `aula backup ~/aula-backup` | `saved: …` lines; if it can't open the keyboard, see "Permissions" |
| 3 | `aula info` | effect, brightness, battery, side light, knob, OS mode, sleep, as on the keyboard |
| 4 | `aula effect breathing -c blue -b 9` | the keyboard breathes blue |
| 5 | `aula restore ~/aula-backup` | the keyboard looks as before step 4 |
| 6 | `aula effect breathing -c red --rgb ff6000`, then `aula palette breathing` | the keyboard breathes orange; the palette line shows `red=#ff6000` |
| 7 | `aula palette --reset`, then `aula restore ~/aula-backup` | the keyboard looks as before step 6 |
| 8 | Run `aula info` and **keep holding Shift** for 2 seconds, then let go | it waits while Shift is held and finishes after you let go |
| 9 | Run `aula info` and keep holding Shift for 7 seconds | `a key seems to be held down…` |
| 10 | After all of the above | no key repeats by itself |
| 11 | `aula macro list` | `0: M1  [not assigned]` (plus your own macros) |
| 12 | `aula macro set test "text:Merhaba dünya iyi günler" --key y -l 1`, then **Fn+Y** in TextEdit | `Merhaba dünya iyi günler` (with a Turkish Q input source; the message says which layout was used) |
| 13 | `aula macro delete test` | `Deleted macro 'test'`; Fn+Y does what it did before |
| 14 | `aula sleep` | the sleep setting you chose |
| 15 | Open **AULA F75** from Launchpad | window opens; the drawing shows your key colors; the header shows "2.4G dongle · Battery …" |
| 16 | GUI → Lighting: pick another effect, then the old one again | the keyboard follows |
| 17 | GUI → Lighting: pick **breathing**, click the color button next to **Color**, choose any color; then **Factory colors** | the keyboard breathes in that color, then red again; pick your old effect again afterwards |
| 18 | GUI → Device | side light, knob, OS mode, Windows key lock and sleep match `aula info` |
| 19 | GUI → Macros → **Record**, type `deneme`, press Shift+A, Command+C and ←, click **Stop** (don't save) | Steps: `text:denemeA`, `win+c`, `left` |
| 20 | Switch to **Bluetooth**, pair it in System Settings, then `aula devices` and `aula info` | `Bluetooth … (supported)`; info as in step 3 |
| 21 | `aula restore ~/aula-backup` | everything as at the start |

Please also note your macOS version and whether it's an Apple silicon or Intel Mac.
