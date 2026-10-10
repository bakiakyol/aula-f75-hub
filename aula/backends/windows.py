"""Windows backend (not implemented yet).

To provide: find_devices(), open_device(path, mode) -> (Channel, KeyGuard),
detect_layout() and key_name(event), as in aula/backends/linux.py.
"""

from ..errors import AulaError
from .base import Channel, KeyGuard

def find_devices() -> list[dict]:
    raise AulaError("Windows support isn't ready yet")


def open_device(path: str, mode: str) -> tuple[Channel, KeyGuard]:
    raise AulaError("Windows support isn't ready yet")


def detect_layout() -> str:
    return "us"


def key_name(event) -> str | None:
    return None
