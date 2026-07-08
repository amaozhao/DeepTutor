"""Compatibility re-export for the shared provider registry."""

from deeptutor.services.provider_registry import (
    NANOBOT_LLM_PROVIDERS,
    PROVIDER_ALIASES,
    PROVIDERS,
    ProviderSpec,
    canonical_provider_name,
    find_by_model,
    find_by_name,
    find_gateway,
    strip_provider_prefix,
)

__all__ = [
    "ProviderSpec",
    "PROVIDERS",
    "NANOBOT_LLM_PROVIDERS",
    "PROVIDER_ALIASES",
    "canonical_provider_name",
    "find_by_name",
    "find_by_model",
    "find_gateway",
    "strip_provider_prefix",
]
