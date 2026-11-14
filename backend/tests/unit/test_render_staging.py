"""Offline tests for the staging wrapper and supervisor configuration.

No live DB, model, child process, or network service is started.
"""
import base64
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from reposcope.staging_access import allowed_origins, credentials, create_app, protect_app
from reposcope.staging_launcher import load_settings

PASSWORD = "unit-test-password-not-a-secret-123456789"


def settings():
    return {"DATABASE_URL": "postgresql+psycopg://offline:offline@127.0.0.1:1/offline",
            "REPOSCOPE_EXPECTED_DB_HOST": "127.0.0.1", "STAGING_PASSWORD": PASSWORD}


@pytest.fixture
def client():
    core = FastAPI()
    @core.get("/api/health")
    def health():
        return {"status": "ok"}
    @core.post("/api/repos")
    def register():
        return {"accepted": True}
    @core.get("/api/private")
    def private():
        return {"private": True}
    with TestClient(protect_app(core, "staging", PASSWORD, ["https://preview.example"])) as test_client:
        yield test_client


def test_health_is_public(client):
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("path", ["/api/private", "/docs", "/openapi.json", "/api/health/"])
def test_other_reads_require_authentication(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert "Basic" in response.headers["www-authenticate"]


def test_registration_requires_authentication(client):
    assert client.post("/api/repos", json={}).status_code == 401
    assert client.post("/api/repos", json={}, auth=("staging", PASSWORD)).status_code == 200


@pytest.mark.parametrize("user,password", [("wrong", PASSWORD), ("staging", "wrong"), ("", "")])
def test_incorrect_credentials_are_rejected(client, user, password):
    assert client.get("/api/private", auth=(user, password)).status_code == 401


@pytest.mark.parametrize("header", ["Bearer test", "Basic !!!", "Basic", "Basic /w=="])
def test_malformed_authorization_is_rejected(client, header):
    assert client.get("/api/private", headers={"Authorization": header}).status_code == 401


def test_valid_credentials_reach_actual_route(client):
    response = client.get("/api/private", auth=("staging", PASSWORD))
    assert response.status_code == 200 and response.json() == {"private": True}


def test_duplicate_authentication_headers_are_rejected(client):
    encoded = base64.b64encode(f"staging:{PASSWORD}".encode()).decode()
    response = client.get("/api/private", headers=[("Authorization", f"Basic {encoded}"),
                                                  ("Authorization", f"Basic {encoded}")])
    assert response.status_code == 401


def test_allowed_preflight_does_not_authorize_actual_write(client):
    headers = {"Origin": "https://preview.example", "Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "authorization,content-type"}
    response = client.options("/api/repos", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://preview.example"
    response = client.post("/api/repos", json={}, headers={"Origin": "https://preview.example"})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://preview.example"


def test_unknown_origin_preflight_is_rejected(client):
    response = client.options("/api/repos", headers={"Origin": "https://unknown.example",
                              "Access-Control-Request-Method": "POST"})
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("password", ["", "short", "x" * 31])
def test_short_or_missing_password_fails_closed(password):
    with pytest.raises(ValueError):
        credentials({"STAGING_PASSWORD": password})


@pytest.mark.parametrize("origin", ["*", "https://*.example", "https://user:pass@example.com",
                                    "https://example.com/path", "http://example.com", "https://example.com?x=1"])
def test_invalid_origins_are_rejected(origin):
    with pytest.raises(ValueError):
        allowed_origins(origin)


def test_explicit_origins_are_accepted():
    assert allowed_origins("https://preview.example, http://localhost:5173") == [
        "https://preview.example", "http://localhost:5173"]


def test_launcher_configuration_validation_does_not_connect():
    assert load_settings(settings()) == (10000, "127.0.0.1")


@pytest.mark.parametrize("key,value", [("REPOSCOPE_EXPECTED_DB_HOST", "wrong.example"),
    ("REPOSCOPE_EXPECTED_DB_HOST", ""), ("PORT", "0"), ("PORT", "bad"), ("STAGING_PASSWORD", ""),
    ("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")])
def test_invalid_launcher_settings_are_rejected(key, value):
    environ = settings()
    environ[key] = value
    with pytest.raises(ValueError):
        load_settings(environ)


def test_factory_loads_protected_app_without_changing_original(monkeypatch):
    core = FastAPI()
    @core.get("/api/private")
    def private():
        return {"ok": True}
    monkeypatch.setenv("STAGING_PASSWORD", PASSWORD)
    monkeypatch.setenv("STAGING_USERNAME", "staging")
    monkeypatch.setenv("STAGING_CORS_ORIGINS", "")
    monkeypatch.setitem(sys.modules, "reposcope.main", SimpleNamespace(app=core))
    with TestClient(create_app()) as wrapped:
        assert wrapped.get("/api/private").status_code == 401
        assert wrapped.get("/api/private", auth=("staging", PASSWORD)).status_code == 200


def build_module():
    path = Path(__file__).resolve().parents[2] / "render_build.py"
    spec = importlib.util.spec_from_file_location("reposcope_render_build_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_uses_hosted_embeddings_without_local_ml():
    pin, remaining = build_module().partition_requirements(
        "torch==2.14.1\n"
        "sentence-transformers==6.1.0\n"
        "pytest==9.1.1\n"
        "httpx>=0.27,<1\n"
        "fastapi>=0.115,<1\n"
    )

    # Parsed for audit only; the hosted builder does not install this pin.
    assert pin == "2.14.1"
    assert "httpx>=0.27,<1" in remaining
    assert "fastapi>=0.115,<1" in remaining
    assert not any(
        line.startswith(("torch", "sentence-transformers", "pytest"))
        for line in remaining
    )


@pytest.mark.parametrize("source", ["fastapi>=0.115", "torch>=2", "torch==2.14.1\ntorch==2.14.1"])
def test_build_rejects_missing_or_ambiguous_torch_pin(source):
    with pytest.raises(ValueError):
        build_module().partition_requirements(source)


def test_check_mode_starts_no_children(monkeypatch):
    from reposcope import staging_launcher
    for key, value in settings().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("STAGING_CORS_ORIGINS", "")
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setattr(staging_launcher.shutil, "which", lambda _: "git")
    start = MagicMock(side_effect=AssertionError("Must not start a process in check mode"))
    monkeypatch.setattr(staging_launcher.subprocess, "Popen", start)
    assert staging_launcher.main(["--check"]) == 0
    start.assert_not_called()


def test_shutdown_signals_groups_and_reaps_children(monkeypatch):
    from unittest.mock import call
    from reposcope import staging_launcher

    children = [MagicMock(pid=101), MagicMock(pid=202)]
    for child in children:
        child.poll.return_value = 0

    # Supply a test-only sentinel for the Unix-only constant.
    # killpg is also mocked, so no operating-system signal is sent.
    force_kill = object()
    monkeypatch.setattr(
        staging_launcher.signal,
        "SIGKILL",
        force_kill,
        raising=False,
    )

    signal_group = MagicMock()
    monkeypatch.setattr(
        staging_launcher.os,
        "killpg",
        signal_group,
        raising=False,
    )

    staging_launcher.stop_children(children, grace_seconds=0)

    assert signal_group.call_args_list == [
        call(101, staging_launcher.signal.SIGTERM),
        call(202, staging_launcher.signal.SIGTERM),
        call(101, force_kill),
        call(202, force_kill),
    ]

    for child in children:
        child.wait.assert_called_once_with(timeout=5)
