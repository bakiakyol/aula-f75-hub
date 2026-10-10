"""Platform backends: how to find and open the keyboard on this OS.

Each module provides find_devices(), open_device(path, mode), detect_layout()
and GDK_KEYCODES (GTK hardware keycode -> key name, for recording macros).
See base.py for the interfaces.
"""

import sys

if sys.platform.startswith("linux"):
    from .linux import GDK_KEYCODES, detect_layout, find_devices, open_device
elif sys.platform == "win32":
    from .windows import GDK_KEYCODES, detect_layout, find_devices, open_device
elif sys.platform == "darwin":
    from .macos import GDK_KEYCODES, detect_layout, find_devices, open_device
else:
    raise ImportError(f"aula-f75-hub doesn't support {sys.platform}")

__all__ = ["GDK_KEYCODES", "detect_layout", "find_devices", "open_device"]
