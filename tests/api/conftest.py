import pytest


@pytest.fixture(autouse=True)
def authenticated_api_testclient(monkeypatch: pytest.MonkeyPatch):
    """Keep isolated router tests in local-admin mode unless they opt into auth."""
    monkeypatch.setattr("deeptutor.api.routers.auth.AUTH_ENABLED", False, raising=False)
    monkeypatch.setattr("deeptutor.services.auth.AUTH_ENABLED", False, raising=False)
    yield
