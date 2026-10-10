# aula-f75-hub on Windows

Windows support uses the same protocol code as Linux. Only finding and opening the
keyboard is different: it talks to the Windows HID API directly (through `ctypes`),
so there is **no driver and no Python package to install**, and nothing needs
administrator rights.

> Status: new. Please run the [test checklist](#test-checklist) and report what
> happens.

## Installation

1. **Python 3.10 or newer**: `winget install Python.Python.3.12`, or the installer
   from python.org (tick "Add python.exe to PATH").
2. **The code**: `git clone https://github.com/bakiakyol/aula-f75-hub.git`, or
   download the ZIP from GitHub and unpack it somewhere permanent.
3. In that folder, run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```

   This puts the folder on your user `PATH` (so `aula` works in new terminals) and
   adds **AULA F75** to the Start menu. `install.ps1 -Remove` undoes both.
4. Open a **new** terminal and run `aula devices`.

Without installing, `aula.cmd` works from the folder itself: `.\aula.cmd info`.

## Graphical interface

The GUI is GTK 3, which on Windows comes from MSYS2:

1. `winget install MSYS2.MSYS2`
2. Open **MSYS2 UCRT64** from the Start menu and run:

   ```sh
   pacman -S --needed mingw-w64-ucrt-x86_64-gtk3 mingw-w64-ucrt-x86_64-python-gobject
   ```

3. Start **AULA F75** from the Start menu, or run `aula-gui.cmd`.

If MSYS2 isn't in `C:\msys64`, set the `AULA_MSYS2` environment variable to its
folder. `install.ps1` tells you whether the GUI is ready.

## Good to know

- **Close the official AULA app** (and other keyboard tools) first. Windows only lets
  one program open the configuration channel; otherwise you get "access denied".
- Relative paths are relative to the install folder (`aula.cmd` runs from there). Use
  full paths for backups, e.g. `aula backup %USERPROFILE%\aula-backup`.
- The tool waits until no key is held before it talks to the keyboard (see
  "Troubleshooting" in the README). On Windows it checks this with
  `GetAsyncKeyState`, which also sees other keyboards.
- Macro `text:` steps follow the Windows keyboard layout: Turkish Q (`0000041F`) is
  detected, everything else is treated as US.
- Recording macros in the GUI uses the keys' scan codes, so it records positions
  whatever the layout.

## Test checklist

Run these in order with the keyboard on the **2.4G dongle** (switch on the back on
2.4G). Write down anything that doesn't match. If a command fails, copy its whole
output. Leave the keyboard alone while a command runs, unless a step says otherwise.

| # | Do | Expected |
|---|---|---|
| 1 | `aula devices` | one line: `2.4G dongle … (supported)` |
| 2 | `aula backup %USERPROFILE%\aula-backup` | `saved: …` lines; files appear in that folder |
| 3 | `aula info` | effect, brightness, battery, side light, knob, OS mode, sleep, as on the keyboard |
| 4 | `aula effect breathing -c blue -b 9` | the keyboard breathes blue |
| 5 | `aula restore %USERPROFILE%\aula-backup` | the keyboard looks as before step 4 |
| 6 | `aula effect breathing -c red --rgb ff6000`, then `aula palette breathing` | the keyboard breathes orange; the palette line shows `red=#ff6000` |
| 7 | `aula palette --reset`, then `aula restore %USERPROFILE%\aula-backup` | the keyboard looks as before step 6 |
| 8 | Run `aula info` and **keep holding Shift** for 2 seconds, then let go | it waits while Shift is held and finishes after you let go |
| 9 | Run `aula info` and keep holding Shift for 7 seconds | `a key seems to be held down…` |
| 10 | After all of the above | no key repeats by itself (e.g. no endless Enter) |
| 11 | `aula macro list` | `0: M1  [not assigned]` (plus your own macros) |
| 12 | `aula macro set test "text:Merhaba dünya, iyi günler!" --key y -l 1`, then **Fn+Y** in Notepad | on a Turkish Q layout it types `Merhaba dünya, iyi günler!` |
| 13 | `aula macro delete test` | `Deleted macro 'test'`; Fn+Y does what it did before |
| 14 | `aula sleep` | the sleep setting you chose |
| 15 | GUI from the Start menu | window opens; the drawing shows your key colors; the header shows "2.4G dongle · Battery …" |
| 16 | GUI → Lighting: pick another effect, then the old one again | the keyboard follows |
| 17 | GUI → Lighting: pick **breathing**, click the color button next to **Color**, choose any color; then **Factory colors** | the keyboard breathes in that color, then red again; pick your old effect again afterwards |
| 18 | GUI → Device | side light, knob, OS mode, Windows key lock and sleep match `aula info` |
| 19 | GUI → Macros → **Record**, type `deneme`, press Shift+A, Ctrl+C and ←, click **Stop** (don't save) | Steps: `text:denemeA`, `ctrl+c`, `left` |
| 20 | Switch to **Bluetooth**, pair it in Windows settings, then `aula devices` and `aula info` | `Bluetooth … (supported)`; info as in step 3 |
| 21 | `aula restore %USERPROFILE%\aula-backup` | everything as at the start |

Please also note your Windows version (`winver`) and `py --version`.
