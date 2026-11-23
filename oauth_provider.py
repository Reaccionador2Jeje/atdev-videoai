#!/usr/bin/env python3
"""Small self-hosted OAuth 2.1 provider for AtDev VideoAI MCP.

This is a single-account starter provider. Use an established identity provider
for multi-user or production deployments. State is persisted in SQLite.
"""
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ATDEV_OAUTH_DB", str(ROOT / "oauth.sqlite3")))
BASE_URL = os.environ.get("ATDEV_PUBLIC_BASE_URL", "").rstrip("/")
RESOURCE = BASE_URL + "/mcp" if BASE_URL else ""
ISSUER = BASE_URL
SCOPES = {"videoai.read", "videoai.write", "videoai.render", "offline_access"}
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 24 * 3600


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id TEXT PRIMARY KEY,
                redirect_uris TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending (
                request_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_codes (
                code_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                challenge TEXT NOT NULL,
                scope TEXT NOT NULL,
                resource TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS access_tokens (
                token_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                resource TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                resource TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );
        """)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _clean_redirect(uri):
    if not isinstance(uri, str) or len(uri) > 2048:
        return False
    try:
        parsed = urlsplit(uri)
        if not parsed.netloc or parsed.fragment or parsed.username or parsed.password:
            return False
        if parsed.scheme == "https":
            return bool(parsed.hostname)
        return parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost") and parsed.port is not None
    except ValueError:
        return False


def initialize():
    with _db():
        pass


def metadata():
    if not BASE_URL:
        return {"error": "ATDEV_PUBLIC_BASE_URL is required for OAuth discovery."}
    return {
        "issuer": ISSUER,
        "authorization_response_iss_parameter_supported": True,
        "authorization_endpoint": ISSUER + "/oauth/authorize",
        "token_endpoint": ISSUER + "/oauth/token",
        "registration_endpoint": ISSUER + "/oauth/register",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": sorted(SCOPES),
    }


def protected_resource_metadata():
    if not RESOURCE:
        return {"error": "ATDEV_PUBLIC_BASE_URL is required for OAuth discovery."}
    return {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "bearer_methods_supported": ["header"],
        "scopes_supported": sorted(SCOPES),
    }


def register_client(payload):
    if not isinstance(payload, dict):
        raise ValueError("Client metadata must be a JSON object.")
    redirects = payload.get("redirect_uris")
    if not isinstance(redirects, list) or not redirects or len(redirects) > 10:
        raise ValueError("redirect_uris must contain 1 to 10 URLs.")
    if any(not _clean_redirect(uri) for uri in redirects):
        raise ValueError("Only HTTPS and localhost redirect URIs are allowed.")
    if payload.get("token_endpoint_auth_method", "none") != "none":
        raise ValueError("Only public OAuth clients using token_endpoint_auth_method=none are supported.")
    grants = payload.get("grant_types", ["authorization_code", "refresh_token"])
    responses = payload.get("response_types", ["code"])
    if not isinstance(grants, list) or not isinstance(responses, list):
        raise ValueError("grant_types and response_types must be arrays.")
    if set(grants) - {"authorization_code", "refresh_token"} or not {"authorization_code", "refresh_token"}.issubset(set(grants)):
        raise ValueError("Both authorization_code and refresh_token grant types are required.")
    if responses != ["code"]:
        raise ValueError("Only the authorization code response type is supported.")
    client_id = "atdev_" + secrets.token_urlsafe(24)
    with _db() as db:
        db.execute("INSERT INTO clients VALUES (?, ?, ?)",
                   (client_id, json.dumps(redirects), int(time.time())))
    return {
        "client_id": client_id,
        "client_name": str(payload.get("client_name", "MCP client"))[:120],
        "redirect_uris": redirects,
        "token_endpoint_auth_method": "none",
        "grant_types": grants,
        "response_types": responses,
    }


def _client(client_id):
    with _db() as db:
        row = db.execute("SELECT * FROM clients WHERE client_id=?", (client_id,)).fetchone()
    return row


def begin_authorization(query):
    if not os.environ.get("ATDEV_OAUTH_USERNAME") or not os.environ.get("ATDEV_OAUTH_PASSWORD"):
        raise RuntimeError("Set ATDEV_OAUTH_USERNAME and ATDEV_OAUTH_PASSWORD before enabling OAuth.")
    if len(os.environ.get("ATDEV_OAUTH_PASSWORD", "")) < 16:
        raise RuntimeError("ATDEV_OAUTH_PASSWORD must contain at least 16 characters.")
    client_id = query.get("client_id", "")
    client = _client(client_id)
    if not client:
        raise ValueError("Unknown OAuth client.")
    redirect_uri = query.get("redirect_uri", "")
    redirects = json.loads(client["redirect_uris"])
    if redirect_uri not in redirects:
        raise ValueError("redirect_uri is not registered for this client.")
    if query.get("response_type") != "code":
        raise ValueError("Only response_type=code is supported.")
    challenge = query.get("code_challenge", "")
    if query.get("code_challenge_method") != "S256" or not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge):
        raise ValueError("PKCE with S256 is required.")
    requested = set(query.get("scope", "videoai.read videoai.write videoai.render").split())
    if not requested or requested - SCOPES:
        raise ValueError("One or more requested OAuth scopes are unsupported.")
    resource = query.get("resource") or RESOURCE
    if resource != RESOURCE:
        raise ValueError("Invalid OAuth resource audience.")
    request_id = secrets.token_urlsafe(24)
    data = {
        "client_id": client_id, "redirect_uri": redirect_uri,
        "state": query.get("state", ""), "challenge": challenge,
        "scope": " ".join(sorted(requested)), "resource": resource,
    }
    with _db() as db:
        db.execute("INSERT INTO pending VALUES (?, ?, ?)",
                   (request_id, json.dumps(data), int(time.time()) + 600))
    return request_id, data


def authorization_page(request_id, data, error=None):
    scopes = html.escape(data["scope"])
    rid = html.escape(request_id, quote=True)
    message = ("<p class='error'>" + html.escape(error) + "</p>") if error else ""
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect AtDev VideoAI</title>
<style>
body{margin:0;background:#101712;color:#eef5ed;font:16px system-ui;display:grid;min-height:100vh;place-items:center}
main{width:min(440px,calc(100% - 40px));padding:28px;background:#1b2920;border:1px solid #344a39;border-radius:18px;box-sizing:border-box}
h1{font-size:24px;margin:0 0 8px}p{color:#c3d1c4;line-height:1.5}
label{display:block;margin:14px 0 6px}input{box-sizing:border-box;width:100%;padding:12px;border-radius:9px;border:1px solid #607563;background:#101712;color:white}
button{margin-top:20px;width:100%;padding:13px;border:0;border-radius:9px;background:#b7e3a4;color:#102015;font-weight:700}
small{color:#9eb1a0}.error{color:#ffb5a8}
</style><main><h1>Connect AtDev VideoAI</h1>
<p>Sign in to authorize ChatGPT to use your AtDev VideoAI project tools.</p>
<p><b>Requested permissions:</b><br>""" + scopes + """</p>""" + message + """
<form method="post" action="/oauth/authorize">
<input type="hidden" name="request_id" value="""" + rid + """">
<label for="username">Account</label><input id="username" name="username" autocomplete="username" required>
<label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<label><input style="width:auto" type="checkbox" name="approve" value="yes" required> I approve these permissions.</label>
<button type="submit">Authorize ChatGPT</button></form>
<p><small>Credentials are checked by your AtDev VideoAI server. Never enter your ChatGPT password here.</small></p>
</main></html>"""


def complete_authorization(form):
    request_id = form.get("request_id", "")
    with _db() as db:
        row = db.execute("SELECT * FROM pending WHERE request_id=?", (request_id,)).fetchone()
    if not row or row["expires_at"] < int(time.time()):
        raise ValueError("Authorization request expired. Start the connection again.")
    if form.get("approve") != "yes":
        raise PermissionError("Authorization was not approved.")
    username = os.environ.get("ATDEV_OAUTH_USERNAME", "")
    password = os.environ.get("ATDEV_OAUTH_PASSWORD", "")
    if not hmac.compare_digest(form.get("username", ""), username):
        raise PermissionError("Account or password is incorrect.")
    if not hmac.compare_digest(form.get("password", ""), password):
        raise PermissionError("Account or password is incorrect.")
    data = json.loads(row["data"])
    code = secrets.token_urlsafe(32)
    with _db() as db:
        db.execute("INSERT INTO auth_codes VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (_hash(code), data["client_id"], data["redirect_uri"],
                    data["challenge"], data["scope"], data["resource"],
                    int(time.time()) + 180))
        db.execute("DELETE FROM pending WHERE request_id=?", (request_id,))
    separator = "&" if "?" in data["redirect_uri"] else "?"
    return data["redirect_uri"] + separator + urlencode({
        "code": code, "state": data["state"], "iss": ISSUER
    })



def pending_authorization(request_id):
    with _db() as db:
        row = db.execute("SELECT * FROM pending WHERE request_id=?", (request_id,)).fetchone()
    if not row or row["expires_at"] < int(time.time()):
        return None
    return json.loads(row["data"])


def authorization_error_redirect(query, description):
    client = _client(query.get("client_id", ""))
    if not client:
        return None
    redirect_uri = query.get("redirect_uri", "")
    if redirect_uri not in json.loads(client["redirect_uris"]):
        return None
    separator = "&" if "?" in redirect_uri else "?"
    return redirect_uri + separator + urlencode({
        "error": "invalid_request",
        "error_description": str(description)[:240],
        "state": query.get("state", ""),
        "iss": ISSUER,
    })

def token_endpoint(form):
    grant = form.get("grant_type")
    if grant == "authorization_code":
        code = form.get("code", "")
        client_id = form.get("client_id", "")
        redirect_uri = form.get("redirect_uri", "")
        verifier = form.get("code_verifier", "")
        with _db() as db:
            # Claim the one-time authorization code under a write lock so two
            # concurrent token requests cannot both exchange the same code.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM auth_codes WHERE code_hash=?", (_hash(code),)).fetchone()
            if row:
                db.execute("DELETE FROM auth_codes WHERE code_hash=?", (_hash(code),))
        if not row or row["expires_at"] < int(time.time()) or row["client_id"] != client_id or row["redirect_uri"] != redirect_uri:
            raise ValueError("invalid_grant")
        if form.get("resource") and form["resource"] != row["resource"]:
            raise ValueError("invalid_grant")
        if not __import__("re").fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
            raise ValueError("invalid_grant")
        derived = __import__("base64").urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(derived, row["challenge"]):
            raise ValueError("invalid_grant")
        scope, resource = row["scope"], row["resource"]
    elif grant == "refresh_token":
        refresh = form.get("refresh_token", "")
        client_id = form.get("client_id", "")
        with _db() as db:
            # Validate before consuming, then atomically claim the refresh token.
            # BEGIN IMMEDIATE prevents concurrent requests from both rotating it.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM refresh_tokens WHERE token_hash=?", (_hash(refresh),)).fetchone()
            if not row or row["expires_at"] < int(time.time()) or row["client_id"] != client_id:
                raise ValueError("invalid_grant")
            if form.get("resource") and form["resource"] != row["resource"]:
                raise ValueError("invalid_grant")
            requested_scope = set(form.get("scope", row["scope"]).split())
            if not requested_scope or requested_scope - set(row["scope"].split()):
                raise ValueError("invalid_scope")
            scope = " ".join(sorted(requested_scope))
            resource = row["resource"]
            db.execute("DELETE FROM refresh_tokens WHERE token_hash=?", (_hash(refresh),))
    else:
        raise ValueError("unsupported_grant_type")

    access = secrets.token_urlsafe(40)
    refresh = secrets.token_urlsafe(48)
    now = int(time.time())
    with _db() as db:
        db.execute("INSERT INTO access_tokens VALUES (?, ?, ?, ?, ?)",
                   (_hash(access), client_id, scope, resource, now + ACCESS_TTL))
        db.execute("INSERT INTO refresh_tokens VALUES (?, ?, ?, ?, ?)",
                   (_hash(refresh), client_id, scope, resource, now + REFRESH_TTL))
    return {
        "access_token": access, "token_type": "Bearer",
        "expires_in": ACCESS_TTL, "refresh_token": refresh,
        "scope": scope,
    }


def verify_access_token(token, required_scope):
    if not token:
        return False
    with _db() as db:
        row = db.execute("SELECT * FROM access_tokens WHERE token_hash=?", (_hash(token),)).fetchone()
    if not row or row["expires_at"] < int(time.time()) or row["resource"] != RESOURCE:
        return False
    return required_scope in row["scope"].split()
