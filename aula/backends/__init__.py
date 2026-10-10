"""Platform backends: how to find and open the keyboard on this OS.

Each module provides find_devices(), open_device(path, mode), detect_layout()
and key_name(event) (GTK key event -> key name, for recording macros).
See base.py for the interfaces.
"""

import sys

if sys.platform.startswith("linux"):
    from .linux import detect_layout, find_devices, key_name, open_device
elif sys.platform == "win32":
    from .windows import detect_layout, find_devices, key_name, open_device
elif sys.platform == "darwin":
    from .macos import detect_layout, find_devices, key_name, open_device
else:
    raise ImportError(f"aula-f75-hub doesn't support {sys.platform}")

__all__ = ["detect_layout", "find_devices", "key_name", "open_device"]
