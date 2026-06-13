"""Server-side model grant resolution and redacted model views.

Grants carry LLM assignments only (grant v2): embedding and search always
resolve from the deployment's active profiles, so per-user grants for them
were never enforced and are not stored.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from deeptutor.services.config.model_catalog import ModelCatalogService
from deeptutor.services.model_selection import LLMSelection, list_llm_options

from .context import get_current_user
from .grants import load_grant
from .paths import get_admin_path_service, get_current_path_service

SERVICES = ("llm", "embedding", "search")
LLM_SOURCE_ADMIN = "admin"
LLM_SOURCE_USER = "user"


def admin_catalog_service() -> ModelCatalogService:
    from deeptutor.services.config import get_model_catalog_service

    return get_model_catalog_service()


def admin_catalog() -> dict[str, Any]:
    return admin_catalog_service().load()


def user_catalog_service() -> ModelCatalogService:
    return ModelCatalogService.get_instance(get_current_path_service().get_settings_file("model_catalog"))


def _load_catalog(service: ModelCatalogService, *, hydrate_from_env: bool) -> dict[str, Any]:
    try:
        return service.load(hydrate_from_env=hydrate_from_env)
    except TypeError:
        return service.load()


def user_catalog() -> dict[str, Any]:
    return _load_catalog(user_catalog_service(), hydrate_from_env=False)


def _profile_by_id(catalog: dict[str, Any], service: str, profile_id: str) -> dict[str, Any] | None:
    for profile in catalog.get("services", {}).get(service, {}).get("profiles", []) or []:
        if str(profile.get("id") or "") == profile_id:
            return profile
    return None


def _model_by_id(profile: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    for model in profile.get("models", []) or []:
        if str(model.get("id") or "") == model_id:
            return model
    return None


def redacted_model_access(user_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    user = get_current_user()
    if user_id is None:
        user_id = user.id
    grant = load_grant(user_id)
    catalog = admin_catalog()
    result: dict[str, list[dict[str, Any]]] = {"llm": []}
    for item in grant.get("models", {}).get("llm", []) or []:
        profile_id = str(item.get("profile_id") or item.get("id") or "")
        profile = _profile_by_id(catalog, "llm", profile_id)
        if not profile:
            result["llm"].append(
                {
                    "profile_id": profile_id,
                    "name": item.get("name") or profile_id or "Unavailable profile",
                    "source": "admin",
                    "available": False,
                }
            )
            continue
        for model_id in item.get("model_ids") or []:
            model = _model_by_id(profile, str(model_id))
            result["llm"].append(
                {
                    "profile_id": profile_id,
                    "model_id": str(model_id),
                    "name": (model or {}).get("name") or str(model_id),
                    "model": (model or {}).get("model") or "",
                    "source": "admin",
                    "available": model is not None,
                }
            )
    return result


def _with_source(payload: dict[str, Any], source: str) -> dict[str, Any]:
    tagged = deepcopy(payload)
    active = tagged.get("active")
    if isinstance(active, dict):
        active["source"] = source
    for option in tagged.get("options", []) or []:
        if isinstance(option, dict):
            option["source"] = source
    return tagged


def _selection_payload(option: dict[str, Any]) -> dict[str, str]:
    payload = {
        "profile_id": str(option.get("profile_id") or ""),
        "model_id": str(option.get("model_id") or ""),
    }
    source = str(option.get("source") or "")
    if source:
        payload["source"] = source
    return payload


def _admin_granted_llm_options(user_id: str) -> list[dict[str, Any]]:
    return [
        {
            "profile_id": item.get("profile_id"),
            "model_id": item.get("model_id"),
            "profile_name": item.get("name") or item.get("profile_id") or "LLM",
            "model_name": item.get("name") or item.get("model") or item.get("model_id"),
            "label": item.get("name") or item.get("model") or item.get("model_id"),
            "model": item.get("model") or "",
            "provider": "",
            "source": LLM_SOURCE_ADMIN,
            "is_active_default": False,
        }
        for item in redacted_model_access(user_id).get("llm", [])
        if item.get("available")
    ]


def _selection_exists_in_catalog(
    catalog: dict[str, Any],
    *,
    profile_id: str,
    model_id: str,
) -> bool:
    profile = _profile_by_id(catalog, "llm", profile_id)
    return bool(profile and _model_by_id(profile, model_id))


def _selection_is_admin_granted(user_id: str, *, profile_id: str, model_id: str) -> bool:
    for item in redacted_model_access(user_id).get("llm", []):
        if item.get("profile_id") == profile_id and item.get("model_id") == model_id:
            return bool(item.get("available"))
    return False


def allowed_llm_options() -> dict[str, Any]:
    user = get_current_user()
    if user.is_admin:
        return _with_source(list_llm_options(admin_catalog()), LLM_SOURCE_ADMIN)

    personal = _with_source(list_llm_options(user_catalog()), LLM_SOURCE_USER)
    options = [*personal.get("options", []), *_admin_granted_llm_options(user.id)]
    active = None
    for option in options:
        if option.get("is_active_default"):
            active = _selection_payload(option)
            break
    if active is None and options:
        active = _selection_payload(options[0])
    return {"active": active, "options": options}


def apply_allowed_llm_selection(selection: dict[str, Any] | None) -> dict[str, Any] | None:
    """Allow only personal or admin-granted LLM profile/model selections."""
    user = get_current_user()
    if user.is_admin or not selection:
        return selection
    profile_id = str(selection.get("profile_id") or "")
    model_id = str(selection.get("model_id") or "")
    source = str(selection.get("source") or "").strip()

    if source == LLM_SOURCE_USER:
        if _selection_exists_in_catalog(user_catalog(), profile_id=profile_id, model_id=model_id):
            return {**selection, "source": LLM_SOURCE_USER}
        raise PermissionError("This personal model is not configured for your account.")

    if source == LLM_SOURCE_ADMIN:
        if _selection_is_admin_granted(user.id, profile_id=profile_id, model_id=model_id):
            return {**selection, "source": LLM_SOURCE_ADMIN}
        raise PermissionError("This model is not assigned to your account.")

    if _selection_exists_in_catalog(user_catalog(), profile_id=profile_id, model_id=model_id):
        return {**selection, "source": LLM_SOURCE_USER}
    if _selection_is_admin_granted(user.id, profile_id=profile_id, model_id=model_id):
        return {**selection, "source": LLM_SOURCE_ADMIN}
    raise PermissionError("This model is not assigned to your account.")


def llm_catalog_context_for_selection(
    selection: dict[str, Any] | LLMSelection | None,
) -> tuple[ModelCatalogService, dict[str, Any], bool]:
    """Return catalog service, catalog payload, and whether env fallback is allowed."""
    user = get_current_user()
    if user.is_admin or selection is None:
        service = admin_catalog_service()
        return service, service.load(), True

    payload = selection.to_dict() if isinstance(selection, LLMSelection) else dict(selection)
    source = str(payload.get("source") or "").strip()
    if source == LLM_SOURCE_USER:
        service = user_catalog_service()
        return service, _load_catalog(service, hydrate_from_env=False), False
    if source == LLM_SOURCE_ADMIN:
        service = admin_catalog_service()
        return service, service.load(), True

    profile_id = str(payload.get("profile_id") or "")
    model_id = str(payload.get("model_id") or "")
    personal = user_catalog()
    if _selection_exists_in_catalog(personal, profile_id=profile_id, model_id=model_id):
        return user_catalog_service(), personal, False
    service = admin_catalog_service()
    return service, service.load(), True


def redacted_catalog_summary() -> dict[str, Any]:
    return {"model_access": deepcopy(redacted_model_access())}
