"""Setup service exports."""

from __future__ import annotations

import importlib

__all__ = [
    "init_user_directories",
    "get_backend_port",
    "get_frontend_port",
    "get_ports",
]


def __getattr__(name: str):
    if name in __all__:
        module = importlib.import_module(f"{__name__}.init")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
