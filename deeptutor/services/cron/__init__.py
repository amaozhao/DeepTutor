"""Built-in cron — scheduled tasks for chat and partners."""

from __future__ import annotations

import importlib

__all__ = [
    "CronJob",
    "CronOwner",
    "CronSchedule",
    "CronService",
    "compute_next_run",
    "get_cron_service",
    "validate_schedule",
]


def __getattr__(name: str):
    module = importlib.import_module(f"{__name__}.service")
    if name in __all__:
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
