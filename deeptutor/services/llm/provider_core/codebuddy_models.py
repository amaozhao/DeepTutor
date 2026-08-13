"""Model catalog lookup for CodeBuddy.

The cloud has no public model-list route, so the catalog comes from the config
the CodeBuddy CLI caches on disk. The CLI subprocess probe is only used as a
fallback, and ``default`` resolves on every deployment.
"""

from __future__ import annotations

import importlib.util

from deeptutor.services.codebuddy_credentials import FALLBACK_MODEL_CATALOG, cached_model_catalog


async def fetch_codebuddy_models(api_key: str | None = None) -> list[str]:
    """Return the model ids available to the signed-in CodeBuddy account."""
    cached = cached_model_catalog()
    if cached:
        return cached

    if importlib.util.find_spec("codebuddy_agent_sdk") is not None:
        provider_module = importlib.import_module(
            "deeptutor.services.llm.provider_core.codebuddy_provider"
        )

        try:
            models = await provider_module.fetch_codebuddy_models(api_key)
        except Exception:  # noqa: BLE001 - CLI probe is best effort
            models = []
        if models:
            return models

    return list(FALLBACK_MODEL_CATALOG)


__all__ = ["fetch_codebuddy_models"]
