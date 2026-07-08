"""Configuration helpers backed by runtime files under data/user/settings."""

from __future__ import annotations

import importlib

# Re-export the loader module itself for code paths that monkeypatch via the
# package namespace, e.g. ``deeptutor.services.config.loader.PROJECT_ROOT``.
loader = importlib.import_module(f"{__name__}.loader")

__all__ = [
    "LaunchSettings",
    "load_launch_settings",
    "PROJECT_ROOT",
    "get_runtime_settings_dir",
    "load_config_with_main",
    "resolve_config_path",
    "get_path_from_config",
    "parse_language",
    "get_agent_params",
    "get_chat_params",
    "DEFAULT_CHAT_PARAMS",
    "ResolvedLLMConfig",
    "ResolvedEmbeddingConfig",
    "ResolvedSearchConfig",
    "resolve_llm_runtime_config",
    "resolve_embedding_runtime_config",
    "resolve_search_runtime_config",
    "search_provider_state",
    "NANOBOT_LLM_PROVIDERS",
    "SUPPORTED_SEARCH_PROVIDERS",
    "DEPRECATED_SEARCH_PROVIDERS",
    "KnowledgeBaseConfigService",
    "get_kb_config_service",
    "ModelCatalogService",
    "get_model_catalog_service",
    "ConfigTestRunner",
    "TestRun",
    "get_config_test_runner",
    "ChatAttachmentLimits",
    "RuntimeSettingsService",
    "ensure_runtime_settings_files",
    "export_runtime_settings_to_env",
    "get_chat_attachment_limits",
    "get_runtime_settings_service",
    "get_ws_max_size",
    "load_auth_settings",
    "load_graphrag_settings",
    "load_integrations_settings",
    "load_shared_state_settings",
    "load_lightrag_settings",
    "load_llamaindex_settings",
    "load_mineru_settings",
    "load_system_settings",
    "loader",
]

_LOADER_EXPORTS = {
    "DEFAULT_CHAT_PARAMS",
    "PROJECT_ROOT",
    "get_agent_params",
    "get_chat_params",
    "get_path_from_config",
    "get_runtime_settings_dir",
    "load_config_with_main",
    "parse_language",
    "resolve_config_path",
}

_PROVIDER_RUNTIME_EXPORTS = {
    "DEPRECATED_SEARCH_PROVIDERS",
    "NANOBOT_LLM_PROVIDERS",
    "SUPPORTED_SEARCH_PROVIDERS",
    "ResolvedLLMConfig",
    "ResolvedEmbeddingConfig",
    "ResolvedSearchConfig",
    "resolve_embedding_runtime_config",
    "resolve_llm_runtime_config",
    "resolve_search_runtime_config",
    "search_provider_state",
}

_KNOWLEDGE_BASE_EXPORTS = {
    "KnowledgeBaseConfigService",
    "get_kb_config_service",
}

_MODEL_CATALOG_EXPORTS = {
    "ModelCatalogService",
    "get_model_catalog_service",
}

_RUNTIME_SETTINGS_EXPORTS = {
    "ChatAttachmentLimits",
    "RuntimeSettingsService",
    "ensure_runtime_settings_files",
    "export_runtime_settings_to_env",
    "get_chat_attachment_limits",
    "get_runtime_settings_service",
    "get_ws_max_size",
    "load_auth_settings",
    "load_graphrag_settings",
    "load_integrations_settings",
    "load_shared_state_settings",
    "load_lightrag_settings",
    "load_llamaindex_settings",
    "load_mineru_settings",
    "load_system_settings",
}

_LAUNCH_SETTINGS_EXPORTS = {
    "LaunchSettings",
    "load_launch_settings",
}

_TEST_RUNNER_EXPORTS = {
    "ConfigTestRunner",
    "TestRun",
    "get_config_test_runner",
}


def __getattr__(name: str):
    if name in _LOADER_EXPORTS:
        return getattr(loader, name)
    if name in _PROVIDER_RUNTIME_EXPORTS:
        module = importlib.import_module(f"{__name__}.provider_runtime")
        return getattr(module, name)
    if name in _KNOWLEDGE_BASE_EXPORTS:
        module = importlib.import_module(f"{__name__}.knowledge_base_config")
        return getattr(module, name)
    if name in _MODEL_CATALOG_EXPORTS:
        module = importlib.import_module(f"{__name__}.model_catalog")
        return getattr(module, name)
    if name in _RUNTIME_SETTINGS_EXPORTS:
        module = importlib.import_module(f"{__name__}.runtime_settings")
        return getattr(module, name)
    if name in _LAUNCH_SETTINGS_EXPORTS:
        module = importlib.import_module(f"{__name__}.launch_settings")
        return getattr(module, name)
    if name in _TEST_RUNNER_EXPORTS:
        module = importlib.import_module(f"{__name__}.test_runner")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
