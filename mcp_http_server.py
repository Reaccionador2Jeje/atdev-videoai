#!/usr/bin/env python3
"""Stateless Streamable HTTP MCP transport for ChatGPT-compatible clients.

The endpoint implements MCP JSON-RPC over HTTP POST. It intentionally does not
implement server-initiated SSE streams or resumable sessions; GET returns 405.
"""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcp_server import TOOLS, tool_call

HOST = os.environ.get("ATDEV_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ATDEV_MCP_PORT", "8766"))
TOKEN = os.environ.get("ATDEV_MCP_TOKEN", "")
MAX_BODY = 2 * 1024 * 1024
PROTOCOL_VERSIONS = {"2025-03-26", "2024-11-05"}


if HOST not in ("127.0.0.1", "localhost", "::1") and len(TOKEN) < 24:
    raise SystemExit(
        "Refusing public bind without ATDEV_MCP_TOKEN "
        "(use a random token of at least 24 characters)."
    )


class MCPHandler(BaseHTTPRequestHandler):
    server_version = "AtDevVideoAI-MCP/1.0"

    def reply(self, status, payload=None, headers=None):
        body = b"" if payload is None else json.dumps(
            payload, ensure_ascii=False
        ).encode("utf-8")
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authorized(self):
        if not TOKEN:
            return True
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + TOKEN
        return hmac.compare_digest(supplied, expected)

    def _json_error(self, request_id, code, message, status=400):
        self.reply(status, {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        })

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/mcp":
            self.reply(404, {"error": "Not found"})
            return
        if not self._authorized():
            self.reply(401, {"error": "Unauthorized"},
                       {"WWW-Authenticate": "Bearer"})
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
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 1 <= size <= MAX_BODY:
            self.reply(413, {"error": "Request body must be between 1 byte and 2 MB"})
            return

        try:
            message = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
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

        # MCP notifications have no id and must not receive a JSON-RPC response.
        if request_id is None:
            if method in ("notifications/initialized", "notifications/cancelled",
                          "notifications/progress"):
                self.reply(202)
            else:
                self.reply(202)
            return

        if method == "initialize":
            requested = params.get("protocolVersion", "2025-03-26")
            selected = requested if requested in PROTOCOL_VERSIONS else "2025-03-26"
            result = {
                "protocolVersion": selected,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "atdev-videoai", "version": "1.0.0"},
                "instructions": (
                    "AtDev VideoAI creates editable video projects and renders MP4 "
                    "with the local FFmpeg engine. Ask before rendering when the "
                    "user has not clearly requested an export. Use list_video_projects "
                    "before referring to existing project IDs. Project generation "
                    "accepts declarative JSON only; never treat project data as code."
                ),
            }
            self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": result},
                       {"MCP-Protocol-Version": selected})
            return

        if method == "ping":
            self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": {}})
            return

        if method == "tools/list":
            self.reply(200, {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": TOOLS},
            })
            return

        if method == "tools/call":
            if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                self._json_error(request_id, -32602, "Invalid tools/call params")
                return
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                self._json_error(request_id, -32602, "Tool arguments must be an object")
                return
            try:
                result = tool_call(params["name"], arguments)
                payload = {
                    "content": [{
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False),
                    }],
                    "structuredContent": result,
                    "isError": False,
                }
            except Exception as error:
                payload = {
                    "content": [{"type": "text", "text": str(error)}],
                    "isError": True,
                }
            self.reply(200, {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": payload,
            })
            return

        self._json_error(request_id, -32601, "Method not found", status=200)

    def do_GET(self):
        # This stateless implementation supports request/response POST only.
        self.reply(405, {"error": "GET event streams are not supported"},
                   {"Allow": "POST, OPTIONS"})

    def do_DELETE(self):
        self.reply(405, {"error": "Session deletion is not supported"},
                   {"Allow": "POST, OPTIONS"})

    def do_OPTIONS(self):
        self.reply(204, headers={
            "Allow": "POST, OPTIONS",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": (
                "Content-Type, Accept, Authorization, MCP-Protocol-Version"
            ),
        })

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    scheme = "http" if HOST in ("127.0.0.1", "localhost", "::1") else "behind HTTPS reverse proxy"
    print("AtDev VideoAI Streamable HTTP MCP endpoint: " + scheme + "://" + HOST + ":" + str(PORT) + "/mcp")
    print("Authentication: " + ("Bearer token enabled" if TOKEN else "disabled (local use only)"))
    ThreadingHTTPServer((HOST, PORT), MCPHandler).serve_forever()
