#!/usr/bin/env python3
"""OAuth-protected stateless Streamable HTTP MCP transport for AtDev VideoAI."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from mcp_server import TOOLS, tool_call
import oauth_provider as oauth

HOST = os.environ.get("ATDEV_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ATDEV_MCP_PORT", "8766"))
MAX_BODY = 2 * 1024 * 1024
PROTOCOL_VERSIONS = {"2025-03-26", "2024-11-05"}
TOOL_SCOPES = {
    "videoai_health": None,
    "create_video_project": "videoai.write",
    "create_video_from_code": ("videoai.write", "videoai.render"),
    "render_video_project": "videoai.render",
    "list_video_projects": "videoai.read",
    "get_video_download": "videoai.read",
}

if HOST not in ("127.0.0.1", "localhost", "::1") and (
    not oauth.BASE_URL.startswith("https://")
    or not os.environ.get("ATDEV_OAUTH_USERNAME")
    or not os.environ.get("ATDEV_OAUTH_PASSWORD")
    or len(os.environ.get("ATDEV_DOWNLOAD_SECRET", "")) < 32
):
    raise SystemExit(
        "Public bind requires ATDEV_PUBLIC_BASE_URL=https://... and "
        "ATDEV_OAUTH_USERNAME/ATDEV_OAUTH_PASSWORD and a 32+ character ATDEV_DOWNLOAD_SECRET."
    )

oauth.initialize()


class MCPHandler(BaseHTTPRequestHandler):
    server_version = "AtDevVideoAI-MCP/1.1"

    def reply(self, status, payload=None, headers=None):
        body = b"" if payload is None else json.dumps(
            payload, ensure_ascii=False
        ).encode("utf-8")
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def html_reply(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 1 <= size <= MAX_BODY:
            raise ValueError("Request body must be between 1 byte and 2 MB.")
        return self.rfile.read(size)

    def _authorized_transport(self):
        # OAuth is enforced per tool; discovery and initialization stay public.
        return True

    def _json_error(self, request_id, code, message, status=400):
        self.reply(status, {
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message},
        })

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/mcp":
            self.reply(405, {"error": "GET is not supported on the stateless MCP endpoint"},
                       {"Allow": "POST, OPTIONS"})
            return
        if parsed.path == "/.well-known/oauth-authorization-server":
            self.reply(200, oauth.metadata(), {"Cache-Control": "public, max-age=300"})
            return
        if parsed.path == "/.well-known/oauth-protected-resource":
            self.reply(200, oauth.protected_resource_metadata(),
                       {"Cache-Control": "public, max-age=300"})
            return
        if parsed.path == "/oauth/authorize":
            try:
                query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
                request_id, data = oauth.begin_authorization(query)
                self.html_reply(200, oauth.authorization_page(request_id, data))
            except Exception as error:
                destination = oauth.authorization_error_redirect(query, error)
                if destination:
                    self.send_response(302)
                    self.send_header("Location", destination)
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                else:
                    self.html_reply(400, "<h1>Authorization unavailable</h1><p>" +
                                    str(error).replace("&", "&amp;").replace("<", "&lt;") +
                                    "</p>")
            return
        self.reply(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/oauth/register":
            try:
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                    self.reply(415, {"error": "Content-Type must be application/json"})
                    return
                raw = self.read_body()
                payload = json.loads(raw.decode("utf-8"))
                self.reply(201, oauth.register_client(payload),
                           {"Cache-Control": "no-store"})
            except Exception as error:
                self.reply(400, {"error": "invalid_client_metadata",
                                 "error_description": str(error)})
            return

        if parsed.path == "/oauth/token":
            try:
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/x-www-form-urlencoded":
                    self.reply(415, {"error": "Content-Type must be application/x-www-form-urlencoded"})
                    return
                raw = self.read_body().decode("utf-8")
                form = {key: values[-1] for key, values in parse_qs(raw).items()}
                result = oauth.token_endpoint(form)
                self.reply(200, result, {"Cache-Control": "no-store",
                                         "Pragma": "no-cache"})
            except Exception as error:
                self.reply(400, {"error": str(error) if str(error) in
                                 ("invalid_grant", "invalid_scope", "unsupported_grant_type")
                                 else "invalid_grant",
                                 "error_description": "The authorization grant is invalid or expired."},
                           {"Cache-Control": "no-store"})
            return

        if parsed.path == "/oauth/authorize":
            raw = self.read_body().decode("utf-8")
            form = {key: values[-1] for key, values in parse_qs(raw).items()}
            try:
                destination = oauth.complete_authorization(form)
                self.send_response(302)
                self.send_header("Location", destination)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except Exception as error:
                request_id = form.get("request_id", "")
                pending = oauth.pending_authorization(request_id)
                if pending:
                    self.html_reply(403, oauth.authorization_page(request_id, pending, str(error)))
                else:
                    self.html_reply(403, "<h1>Authorization not completed</h1><p>" +
                                    str(error).replace("&", "&amp;").replace("<", "&lt;") +
                                    "</p><p>Return to ChatGPT and start the connection again.</p>")
            return

        if parsed.path != "/mcp":
            self.reply(404, {"error": "Not found"})
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            self.reply(415, {"error": "Content-Type must be application/json"})
            return
        accept = self.headers.get("Accept", "application/json")
        if "application/json" not in accept and "*/*" not in accept:
            self.reply(406, {"error": "This endpoint returns application/json"})
            return
        protocol = self.headers.get("MCP-Protocol-Version")
        if protocol and protocol not in PROTOCOL_VERSIONS:
            self.reply(400, {"error": "Unsupported MCP-Protocol-Version"})
            return
        try:
            message = json.loads(self.read_body().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._json_error(None, -32700, "Parse error")
            return
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            self._json_error(message.get("id") if isinstance(message, dict) else None,
                             -32600, "Invalid JSON-RPC request")
            return
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            self._json_error(request_id, -32602, "Request params must be an object")
            return
        if request_id is None:
            self.reply(202)
            return
        if method == "initialize":
            requested = params.get("protocolVersion", "2025-03-26")
            selected = requested if requested in PROTOCOL_VERSIONS else "2025-03-26"
            self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": selected,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "atdev-videoai", "version": "1.1.0"},
                "instructions": (
                    "AtDev VideoAI creates editable video projects and renders motion-graphic MP4 "
                    "videos with FFmpeg. It combines titles, text, images, transitions, "
                    "animation and audio; it does not generate AI footage or voice. "
                    "Use create_video_project for editable projects and "
                    "create_video_from_code for valid declarative JSON (never execute it). "
                    "Only render when the user explicitly asks for an MP4/export. "
                    "For saved projects, list_video_projects first if the project ID is unknown, "
                    "then render_video_project. Return the temporary download URL from the render. "
                    "Download links expire after 15 minutes. Health is public; project and render "
                    "actions require OAuth scopes."
                ),
            }}, {"MCP-Protocol-Version": selected})
            return
        if method == "ping":
            self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": {}})
            return
        if method == "tools/list":
            self.reply(200, {"jsonrpc": "2.0", "id": request_id,
                             "result": {"tools": TOOLS}})
            return
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                self._json_error(request_id, -32602, "Invalid tools/call params")
                return
            if name not in TOOL_SCOPES:
                payload = {"content": [{"type": "text", "text": "Unknown tool."}],
                           "isError": True}
            else:
                scopes = TOOL_SCOPES[name]
                if scopes:
                    if isinstance(scopes, str):
                        scopes = (scopes,)
                    auth = self.headers.get("Authorization", "")
                    bearer = auth[7:].strip() if auth.startswith("Bearer ") else ""
                    if not all(oauth.verify_access_token(bearer, scope) for scope in scopes):
                        metadata_url = (oauth.RESOURCE and
                                        oauth.ISSUER + "/.well-known/oauth-protected-resource")
                        required_scope = " ".join(scopes)
                        challenge = ('Bearer resource_metadata="' + metadata_url +
                                     '", scope="' + required_scope +
                                     '", error="invalid_token", error_description="Connect your AtDev VideoAI account to authorize this action"')
                        payload = {
                            "content": [{"type": "text", "text": "Authentication required. Connect your AtDev VideoAI account."}],
                            "isError": True,
                            "_meta": {"mcp/www_authenticate": [challenge]},
                        }
                    else:
                        payload = self._run_tool(name, arguments)
                else:
                    payload = self._run_tool(name, arguments)
            self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": payload})
            return
        self._json_error(request_id, -32601, "Method not found", status=200)

    def _run_tool(self, name, arguments):
        try:
            result = tool_call(name, arguments)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "structuredContent": result,
                "isError": False,
            }
        except Exception as error:
            return {"content": [{"type": "text", "text": str(error)}], "isError": True}

    def do_OPTIONS(self):
        self.reply(204, headers={
            "Allow": "GET, POST, OPTIONS",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": (
                "Content-Type, Accept, Authorization, MCP-Protocol-Version"
            ),
        })

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    scheme = "http" if HOST in ("127.0.0.1", "localhost", "::1") else "HTTPS reverse proxy required"
    print("AtDev VideoAI MCP: " + scheme + "://" + HOST + ":" + str(PORT) + "/mcp")
    print("OAuth issuer: " + (oauth.ISSUER or "not configured"))
    print("OAuth account configured: " + str(bool(os.environ.get("ATDEV_OAUTH_USERNAME") and os.environ.get("ATDEV_OAUTH_PASSWORD"))))
    print("Per-tool OAuth scopes: enabled")
    ThreadingHTTPServer((HOST, PORT), MCPHandler).serve_forever()
