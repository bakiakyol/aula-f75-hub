#!/bin/sh
# Install / uninstall aula-f75-hub for the current user on macOS.
#   ./install-macos.sh            install (command line + GUI)
#   ./install-macos.sh --no-gui   command line only (no GTK)
#   ./install-macos.sh --remove   uninstall
# Needs Homebrew (https://brew.sh). Nothing is installed system-wide by hand:
# a virtual environment in .venv, ~/.local/bin/aula and ~/Applications/AULA F75.app.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
APP="$HOME/Applications/AULA F75.app"
VENV="$HERE/.venv"

if [ "$1" = "--remove" ]; then
    rm -f "$BIN/aula"
    rm -rf "$APP" "$VENV"
    echo "Removed."
    exit 0
fi

command -v brew >/dev/null || { echo "Homebrew is needed: https://brew.sh"; exit 1; }

if [ "$1" = "--no-gui" ]; then
    brew install python
else
    brew install python gtk+3 pygobject3
fi
PY="$(brew --prefix)/bin/python3"

# hidapi (the bridge to the keyboard) goes into a virtual environment that can
# still see Homebrew's GTK bindings
"$PY" -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade hidapi

mkdir -p "$BIN"
cat > "$BIN/aula" <<EOF
#!/bin/sh
cd "$HERE" && exec "$VENV/bin/python" -m aula "\$@"
EOF
chmod +x "$BIN/aula"

if [ "$1" != "--no-gui" ]; then
    mkdir -p "$APP/Contents/MacOS"
    cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>AULA F75</string>
    <key>CFBundleIdentifier</key><string>io.github.bakiakyol.aula-f75-hub</string>
    <key>CFBundleExecutable</key><string>aula-gui</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
</dict>
</plist>
EOF
    cat > "$APP/Contents/MacOS/aula-gui" <<EOF
#!/bin/sh
cd "$HERE" && exec "$VENV/bin/python" -m aula gui
EOF
    chmod +x "$APP/Contents/MacOS/aula-gui"
    if "$VENV/bin/python" -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
        echo "GUI: ready. Open \"AULA F75\" from Launchpad or ~/Applications."
    else
        echo "GUI: GTK isn't importable from $PY; see docs/macos.md."
    fi
fi

echo "Installed. Run 'aula devices'."
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Add $BIN to your PATH: echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zprofile" ;; esac
