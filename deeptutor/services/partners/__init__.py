"""Partner services — lifecycle, runtime, workspace, and sessions."""

from __future__ import annotations

import importlib

__all__ = [
    "PartnerConfig",
    "PartnerInstance",
    "PartnerManager",
    "PartnerRunner",
    "PartnerSessionStore",
    "get_partner_manager",
    "mask_channel_secrets",
    "slugify_partner_id",
    "slugify_soul_id",
]


def __getattr__(name: str):
    if name in {
        "PartnerConfig",
        "PartnerInstance",
        "PartnerManager",
        "get_partner_manager",
        "mask_channel_secrets",
        "slugify_partner_id",
        "slugify_soul_id",
    }:
        module = importlib.import_module(f"{__name__}.manager")
        return getattr(module, name)
    if name == "PartnerRunner":
        module = importlib.import_module(f"{__name__}.runtime")
        return module.PartnerRunner
    if name == "PartnerSessionStore":
        module = importlib.import_module(f"{__name__}.sessions")
        return module.PartnerSessionStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
