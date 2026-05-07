from __future__ import annotations

import time

from fastapi import HTTPException
import pytest

from deeptutor.api.routers import settings as settings_router
from deeptutor.auth.models import AuthUser


def _user(role: str) -> AuthUser:
    return AuthUser(
        id=f"user_{role}",
        email=f"{role}@example.com",
        password_hash="hash",
        display_name=role,
        created_at=time.time(),
        updated_at=time.time(),
        role=role,
    )


class FakeCatalogService:
    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.saved: dict | None = None
        self.applied: dict | None = None

    def load(self) -> dict:
        return self.catalog

    def save(self, catalog: dict) -> dict:
        self.saved = catalog
        self.catalog = catalog
        return catalog

    def apply(self, catalog: dict) -> dict:
        self.applied = catalog
        self.catalog = catalog
        return {"LLM_API_KEY": catalog["services"]["llm"]["profiles"][0]["api_key"]}


def _catalog() -> dict:
    return {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "llm-profile",
                "active_model_id": "llm-model",
                "profiles": [
                    {
                        "id": "llm-profile",
                        "name": "LLM",
                        "binding": "openai",
                        "base_url": "https://llm.example/v1",
                        "api_key": "llm-secret",
                        "api_version": "",
                        "extra_headers": {"Authorization": "Bearer secret"},
                        "models": [{"id": "llm-model", "name": "M", "model": "m"}],
                    }
                ],
            },
            "embedding": {
                "active_profile_id": "embedding-profile",
                "active_model_id": "embedding-model",
                "profiles": [
                    {
                        "id": "embedding-profile",
                        "name": "Emb",
                        "binding": "openai",
                        "base_url": "https://embedding.example/v1/embeddings",
                        "api_key": "embedding-secret",
                        "api_version": "",
                        "extra_headers": {},
                        "models": [
                            {
                                "id": "embedding-model",
                                "name": "E",
                                "model": "e",
                                "dimension": "1024",
                            }
                        ],
                    }
                ],
            },
            "search": {
                "active_profile_id": "search-profile",
                "profiles": [
                    {
                        "id": "search-profile",
                        "name": "Search",
                        "provider": "brave",
                        "base_url": "",
                        "api_key": "search-secret",
                        "proxy": "http://user:pass@proxy",
                        "models": [],
                    }
                ],
            },
        },
    }


@pytest.mark.asyncio
async def test_non_admin_settings_catalog_is_redacted(monkeypatch) -> None:
    fake = FakeCatalogService(_catalog())
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: fake)

    response = await settings_router.get_catalog(user=_user("user"))

    services = response["catalog"]["services"]
    assert services["llm"]["profiles"][0]["api_key"] == ""
    assert services["llm"]["profiles"][0]["extra_headers"]["Authorization"] == ""
    assert services["embedding"]["profiles"][0]["api_key"] == ""
    assert services["search"]["profiles"][0]["api_key"] == ""
    assert services["search"]["profiles"][0]["proxy"] == ""


@pytest.mark.asyncio
async def test_admin_settings_catalog_keeps_raw_secrets(monkeypatch) -> None:
    fake = FakeCatalogService(_catalog())
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: fake)

    response = await settings_router.get_catalog(user=_user("admin"))

    services = response["catalog"]["services"]
    assert services["llm"]["profiles"][0]["api_key"] == "llm-secret"
    assert services["llm"]["profiles"][0]["extra_headers"]["Authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_non_admin_cannot_update_apply_or_run_provider_tests(monkeypatch) -> None:
    fake = FakeCatalogService(_catalog())
    monkeypatch.setattr(settings_router, "get_model_catalog_service", lambda: fake)

    with pytest.raises(HTTPException) as update_exc:
        await settings_router.update_catalog(
            settings_router.CatalogPayload(catalog=_catalog()),
            user=_user("user"),
        )
    assert update_exc.value.status_code == 403

    with pytest.raises(HTTPException) as apply_exc:
        await settings_router.apply_catalog(
            settings_router.CatalogPayload(catalog=_catalog()),
            user=_user("user"),
        )
    assert apply_exc.value.status_code == 403

    with pytest.raises(HTTPException) as test_exc:
        await settings_router.start_service_test("llm", user=_user("user"))
    assert test_exc.value.status_code == 403


def test_redacted_catalog_does_not_mutate_loaded_catalog() -> None:
    catalog = _catalog()

    redacted = settings_router.redact_catalog_for_user(catalog)

    assert redacted["services"]["llm"]["profiles"][0]["api_key"] == ""
    assert catalog["services"]["llm"]["profiles"][0]["api_key"] == "llm-secret"
