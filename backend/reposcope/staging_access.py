"""Temporary access boundary for the Render feasibility deployment only."""
import base64
import binascii
import hashlib
import hmac
import os
from urllib.parse import urlsplit

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse


def credentials(environ):
    username = environ.get("STAGING_USERNAME", "staging")
    password = environ.get("STAGING_PASSWORD", "")
    if not username or ":" in username or len(password) < 32:
        raise ValueError("Set a staging username and a password of at least 32 characters")
    return username, password


def allowed_origins(value):
    origins = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        parsed = urlsplit(item)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment or "*" in item):
            raise ValueError("CORS origins must be explicit scheme://host[:port] values")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Non-local staging CORS origins must use HTTPS")
        parsed.port  # Reject invalid port syntax.
        origins.append(item)
    return origins


class StagingBasicAuth:
    def __init__(self, app, username, password):
        self.app = app
        self.username_hash = hashlib.sha256(username.encode()).digest()
        self.password_hash = hashlib.sha256(password.encode()).digest()

    def authorized(self, scope):
        headers = [value for key, value in scope.get("headers", []) if key.lower() == b"authorization"]
        if len(headers) != 1 or len(headers[0]) > 4096:
            return False
        try:
            scheme, encoded = headers[0].decode("ascii").split(" ", 1)
            if scheme.lower() != "basic":
                return False
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, UnicodeError, binascii.Error):
            return False
        user_ok = hmac.compare_digest(hashlib.sha256(username.encode()).digest(), self.username_hash)
        password_ok = hmac.compare_digest(hashlib.sha256(password.encode()).digest(), self.password_hash)
        return user_ok and password_ok

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        health = scope.get("path") == "/api/health" and scope.get("method") in {"GET", "HEAD"}
        if health or self.authorized(scope):
            await self.app(scope, receive, send)
            return
        response = JSONResponse({"error": {"code": "UNAUTHORIZED", "status": 401,
            "message": "Staging credentials required", "details": {}}}, status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="RepoScope staging", charset="UTF-8"',
                     "Cache-Control": "no-store"})
        await response(scope, receive, send)


def protect_app(app, username, password, origins):
    # The outer CORS layer handles allowed preflights; actual requests still
    # pass through authentication. This is not the production identity system.
    return CORSMiddleware(StagingBasicAuth(app, username, password),
        allow_origins=origins, allow_credentials=True,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"])


def create_app():
    username, password = credentials(os.environ)
    origins = allowed_origins(os.getenv("STAGING_CORS_ORIGINS", ""))
    from reposcope.main import app
    return protect_app(app, username, password, origins)
