#!/bin/sh
# Install / uninstall aula-f75-hub for the current user.
#   ./install.sh            install
#   ./install.sh --remove   uninstall
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
RULE=/etc/udev/rules.d/70-aula-f75.rules

if [ "$1" = "--remove" ]; then
    rm -f "$BIN/aula" "$APPS/aula-f75-hub.desktop"
    if [ -f "$RULE" ]; then
        echo "Removing udev rule (needs sudo)…"
        sudo rm -f "$RULE" && sudo udevadm control --reload-rules
    fi
    echo "Removed."
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
python3 -c "import gi; gi.require_version('Gtk', '3.0')" 2>/dev/null \
    || echo "Note: the GUI needs GTK 3 for Python (sudo apt install python3-gi gir1.2-gtk-3.0). The CLI works without it."

echo "Installing udev rule so the keyboard can be used without sudo (needs sudo)…"
sudo cp "$HERE/udev/70-aula-f75.rules" "$RULE"
sudo udevadm control --reload-rules
sudo udevadm trigger

mkdir -p "$BIN" "$APPS"
ln -sf "$HERE/aula.sh" "$BIN/aula"
cp "$HERE/data/aula-f75-hub.desktop" "$APPS/"

echo "Installed. Run 'aula gui' or open \"AULA F75\" from the application menu."
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Add $BIN to your PATH (log out and back in on most distros)." ;; esac
