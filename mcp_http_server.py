#!/usr/bin/env python3
"""HTTP MCP transport for remote/self-hosted AtDev VideoAI integrations."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mcp_server import TOOLS, tool_call

HOST = os.environ.get("ATDEV_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ATDEV_MCP_PORT", "8766"))
TOKEN = os.environ.get("ATDEV_MCP_TOKEN", "")

if HOST not in ("127.0.0.1", "localhost", "::1") and len(TOKEN) < 24:
    raise SystemExit("Refusing public bind without ATDEV_MCP_TOKEN (use a random token of at least 24 characters).")

class MCPHandler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/mcp":
            self.reply(404, {"error": "Not found"})
            return
        if TOKEN and self.headers.get("Authorization") != "Bearer " + TOKEN:
            self.reply(401, {"error": "Unauthorized"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 2 * 1024 * 1024:
                self.reply(413, {"error": "Request too large"})
                return
            message = json.loads(self.rfile.read(size))
            method = message.get("method")
            request_id = message.get("id")
            if method == "initialize":
                result = {"protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "atdev-videoai", "version": "0.2.0"}}
                self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": result})
            elif method == "ping":
                self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": {}})
            elif method == "tools/list":
                self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
            elif method == "tools/call":
                params = message.get("params", {})
                try:
                    result = tool_call(params.get("name"), params.get("arguments", {}))
                    payload = {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                               "structuredContent": result, "isError": False}
                except Exception as error:
                    payload = {"content": [{"type": "text", "text": str(error)}], "isError": True}
                self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": payload})
            elif request_id is not None:
                self.reply(200, {"jsonrpc": "2.0", "id": request_id,
                                 "error": {"code": -32601, "message": "Method not found"}})
            else:
                self.send_response(202)
                self.end_headers()
        except Exception as error:
            self.reply(400, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": str(error)}})

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    print("AtDev VideoAI HTTP MCP endpoint: http://" + HOST + ":" + str(PORT) + "/mcp")
    ThreadingHTTPServer((HOST, PORT), MCPHandler).serve_forever()
