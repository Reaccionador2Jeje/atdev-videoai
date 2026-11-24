#!/usr/bin/env python3
"""Authenticated REST facade for configuring AtDev VideoAI as a GPT Action."""
import hmac
import json
import os
import re
from pathlib import Path

from mcp_server import tool_call

ROOT = Path(__file__).resolve().parent
OPENAPI_PATH = ROOT / "docs" / "openapi" / "gpt-actions.json"
MAX_BODY = 2 * 1024 * 1024


def _response(status, payload, headers=None):
    result_headers = {"Cache-Control": "no-store"}
    if headers:
        result_headers.update(headers)
    return status, payload, result_headers


def _authorized(headers):
    expected = os.environ.get("ATDEV_GPT_ACTIONS_API_KEY", "").strip()
    supplied = headers.get("X-AtDev-API-Key", "").strip()
    if len(expected) < 32:
        return False, "GPT Actions API is not configured on this server."
    return hmac.compare_digest(supplied, expected), "A valid X-AtDev-API-Key is required."


def handle_request(method, path, headers, body=b""):
    """Return (status, JSON payload, response headers) for the GPT Actions API."""
    if path == "/actions/openapi.json" and method == "GET":
        try:
            return _response(200, json.loads(OPENAPI_PATH.read_text(encoding="utf-8")),
                             {"Cache-Control": "public, max-age=300"})
        except (OSError, ValueError):
            return _response(500, {"error": "OpenAPI document is unavailable."})

    if not path.startswith("/actions/v1/"):
        return _response(404, {"error": "Not found."})
    authorized, message = _authorized(headers)
    if not authorized:
        status = 503 if len(os.environ.get("ATDEV_GPT_ACTIONS_API_KEY", "").strip()) < 32 else 401
        return _response(status, {"error": message})

    if method == "GET" and path == "/actions/v1/health":
        return _response(200, tool_call("videoai_health", {}))

    if method == "GET" and path == "/actions/v1/projects":
        return _response(200, tool_call("list_video_projects", {}))

    if method == "POST" and path == "/actions/v1/projects":
        try:
            if not isinstance(body, (bytes, bytearray)) or not 1 <= len(body) <= MAX_BODY:
                raise ValueError("Request body must be between 1 byte and 2 MB.")
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("project"), dict):
                raise ValueError("Body must contain a project object.")
            result = tool_call("create_video_from_code", {
                "project_json": json.dumps(payload["project"], ensure_ascii=False),
                "render": bool(payload.get("render", False)),
            })
            return _response(201, result)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            return _response(400, {"error": str(error)})
        except Exception as error:
            return _response(422, {"error": str(error)})

    match = re.fullmatch(r"/actions/v1/projects/([a-f0-9]{12})/render", path)
    if method == "POST" and match:
        try:
            result = tool_call("render_video_project", {"project_id": match.group(1)})
            return _response(200, result)
        except Exception as error:
            return _response(422, {"error": str(error)})

    match = re.fullmatch(r"/actions/v1/renders/(video-[a-f0-9]{12}\\.mp4)/download", path)
    if method == "GET" and match:
        try:
            return _response(200, tool_call("get_video_download", {"filename": match.group(1)}))
        except Exception as error:
            return _response(404, {"error": str(error)})

    return _response(404, {"error": "Unknown AtDev VideoAI action endpoint."})
