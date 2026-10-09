# aula-f75-hub

**English** | [Türkçe](README.tr.md)

A Linux configuration tool for the **AULA F75** keyboard: lighting effects, per-key RGB,
key remapping and backups. The official software is Windows-only (and its lighting
settings are broken there too). This tool talks the keyboard's protocol directly and
needs no extra libraries.

Status: verified over the **2.4G dongle**. Bluetooth uses the same channel (untested).
Wired mode is not supported yet.

## Setup

Install the udev rule once, so the keyboard can be accessed without sudo:

```bash
sudo cp udev/70-aula-f75.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Usage

```bash
./aula.sh devices                         # find the keyboard
./aula.sh info                            # current effect / brightness / speed / color
./aula.sh effects                         # list effects and colors
./aula.sh effect static -c red -b 9       # change effect (-c color, -b brightness 0-9, -s speed 0-4)
./aula.sh brightness 5
./aula.sh side-light breathing            # white bar next to Esc: off | fill | breathing | static
./aula.sh knob lighting                   # knob: media (volume, mute) | lighting (brightness, effect)
./aula.sh os mac                          # OS mode: windows | android | mac
./aula.sh win-lock on                     # disable the Windows key
./aula.sh keys                            # list key names
./aula.sh key-color esc=ff0000 w=00ff00   # per-key colors (switches to the custom effect)
./aula.sh key-color --clear all=0010ff w=ff0000 a=ff0000 s=ff0000 d=ff0000
./aula.sh preset synthwave                # load a built-in color theme (no name: list them)
./aula.sh remap capslock lctrl            # CapsLock -> Ctrl  (undo: remap capslock capslock)
./aula.sh remap f1 esc -l 1               # remap on the Fn layer (layer 1)
./aula.sh backup ~/aula-backup
./aula.sh restore ~/aula-backup
```

On a Turkish Q layout the letters `ğ ü ş ö ç ı` can be used as key names.

`backup/` holds the keyboard's original settings, read before this tool ever wrote
anything. If something goes wrong: `./aula.sh restore backup`

## Tests

```bash
python3 -m unittest -v
```

Protocol details: [docs/protocol.md](docs/protocol.md)
