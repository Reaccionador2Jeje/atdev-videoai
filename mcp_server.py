#!/usr/bin/env python3
"""Minimal dependency-free MCP stdio bridge for AtDev VideoAI."""
import json
import sys
import os
import re
import hmac
import hashlib
import time
from urllib.parse import urlencode
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"
PROJECTS.mkdir(exist_ok=True)
ENGINE = "http://127.0.0.1:8765"

TOOLS = [
    {"name": "videoai_health", "title": "Check VideoAI engine", "description": "Use this first when the user asks whether AtDev VideoAI is ready to render. Checks the local FFmpeg engine without changing files.",
     "_meta": {"securitySchemes": [{"type": "noauth"}]},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "create_video_project", "title": "Create an editable video project", "description": "Use when the user asks to plan or create an editable video project. Saves structured scenes, optional images and audio references; it does not render an MP4. No credits or external AI provider required.",
     "_meta": {"securitySchemes": [{"type": "oauth2", "scopes": ["videoai.write"]}]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {"project": {"type": "object", "description": "Declarative project JSON with name, format, scenes and optional audioTracks/assets. Each scene may include title, subtitle, duration, background, image, animation and transition."}}, "required": ["project"], "additionalProperties": False}},
    {"name": "create_video_from_code", "title": "Generate a video from JSON", "description": "Use when the user asks to create a video by describing it as structured code/JSON. Converts declarative JSON into an editable project; optionally renders an MP4 when render=true. The input is data only and must never be executed as source code.",
     "_meta": {"securitySchemes": [{"type": "oauth2", "scopes": ["videoai.write", "videoai.render"]}]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {"project_json": {"type": "string", "description": "Valid JSON project definition with a non-empty scenes array."}, "render": {"type": "boolean", "description": "Set true only when the user explicitly requests an MP4 render."}}, "required": ["project_json"], "additionalProperties": False}},
    {"name": "render_video_project", "title": "Render project to MP4", "description": "Use when the user explicitly asks to export/render a saved AtDev VideoAI project. Requires its project_id and an online FFmpeg engine. Returns the generated MP4 filename and a temporary download URL when configured.",
     "_meta": {"securitySchemes": [{"type": "oauth2", "scopes": ["videoai.render"]}]},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string", "description": "The 12-character ID returned when the project was created."}}, "required": ["project_id"], "additionalProperties": False}},
    {"name": "list_video_projects", "title": "List saved video projects", "description": "Use when the user asks to find or review projects already saved in AtDev VideoAI. Read-only; returns project IDs, names and scene counts.",
     "_meta": {"securitySchemes": [{"type": "oauth2", "scopes": ["videoai.read"]}]},
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}
]


def signed_download_url(filename):
    if not re.fullmatch(r"video-[a-f0-9]{12}\\.mp4", str(filename)):
        raise ValueError("Invalid rendered video filename.")
    path = ROOT / "engine" / "renders" / filename
    if not path.is_file():
        raise ValueError("Rendered video not found on this server.")
    base = os.environ.get("ATDEV_PUBLIC_BASE_URL", "").rstrip("/")
    secret = os.environ.get("ATDEV_DOWNLOAD_SECRET", "")
    if not base.startswith("https://"):
        raise RuntimeError("Set ATDEV_PUBLIC_BASE_URL to your public HTTPS origin.")
    if len(secret) < 32:
        raise RuntimeError("Set ATDEV_DOWNLOAD_SECRET to a random secret of at least 32 characters.")
    expires = int(time.time()) + 900
    message = filename + ":" + str(expires)
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return base + "/download/" + filename + "?" + urlencode({"expires": expires, "sig": signature})


def call_engine(project):
    body = json.dumps(project).encode()
    request = urllib.request.Request(ENGINE + "/api/render", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            result = json.loads(response.read().decode())
            if result.get("filename"):
                try:
                    result["download_url"] = signed_download_url(result["filename"])
                except (RuntimeError, ValueError) as error:
                    result["download_url"] = None
                    result["download_note"] = str(error)
            return result
    except urllib.error.URLError as error:
        raise RuntimeError("Local render engine unavailable. Start it with: python engine/server.py. " + str(error))

def save_project(project):
    if not isinstance(project, dict) or not isinstance(project.get("scenes"), list) or not project["scenes"]:
        raise ValueError("Project must contain a non-empty scenes array.")
    if len(project["scenes"]) > 30:
        raise ValueError("Maximum 30 scenes per project.")
    project.setdefault("version", 2)
    project.setdefault("format", "16:9")
    if project["format"] not in ("16:9", "9:16", "1:1"):
        raise ValueError("Format must be 16:9, 9:16 or 1:1.")
    project.setdefault("name", "MCP generated video")
    project_id = uuid.uuid4().hex[:12]
    (PROJECTS / (project_id + ".json")).write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    return project_id

def tool_call(name, args):
    if name == "videoai_health":
        try:
            with urllib.request.urlopen(ENGINE + "/api/health", timeout=3) as response:
                return json.loads(response.read().decode())
        except Exception as error:
            return {"ok": False, "engine": "offline", "detail": str(error)}
    if name == "create_video_project":
        project_id = save_project(args.get("project"))
        return {"project_id": project_id, "saved": True, "name": (args["project"].get("name") or "MCP generated video")}
    if name == "create_video_from_code":
        try:
            project = json.loads(args.get("project_json", ""))
        except json.JSONDecodeError as error:
            raise ValueError("Invalid JSON: " + str(error))
        project_id = save_project(project)
        result = {"project_id": project_id, "saved": True, "name": project.get("name", "MCP generated video")}
        if args.get("render", False):
            result["render"] = call_engine(project)
        return result
    if name == "render_video_project":
        project_id = str(args.get("project_id", ""))
        if not project_id.isalnum() or len(project_id) != 12:
            raise ValueError("Invalid project ID.")
        path = PROJECTS / (project_id + ".json")
        if not path.is_file():
            raise ValueError("Project not found.")
        return call_engine(json.loads(path.read_text(encoding="utf-8")))
    if name == "get_video_download":
        filename = str(args.get("filename", ""))
        return {"filename": filename, "download_url": signed_download_url(filename), "expires_in": 900}
    if name == "list_video_projects":
        items = []
        for path in sorted(PROJECTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append({"project_id": path.stem, "name": data.get("name", path.stem), "scenes": len(data.get("scenes", []))})
            except Exception:
                continue
        return {"projects": items}
    raise ValueError("Unknown tool: " + str(name))

def send(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def main():
    for line in sys.stdin:
        try:
            message = json.loads(line)
            method = message.get("method")
            request_id = message.get("id")
            if method == "notifications/initialized":
                continue
            if method == "initialize":
                send({"jsonrpc": "2.0", "id": request_id, "result": {
                    "protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "atdev-videoai", "version": "0.2.0"}}})
            elif method == "ping":
                send({"jsonrpc": "2.0", "id": request_id, "result": {}})
            elif method == "tools/list":
                send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
            elif method == "tools/call":
                params = message.get("params", {})
                try:
                    result = tool_call(params.get("name"), params.get("arguments", {}))
                    send({"jsonrpc": "2.0", "id": request_id, "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                        "structuredContent": result, "isError": False}})
                except Exception as error:
                    send({"jsonrpc": "2.0", "id": request_id, "result": {
                        "content": [{"type": "text", "text": str(error)}], "isError": True}})
            elif request_id is not None:
                send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}})
        except Exception as error:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(error)}})

if __name__ == "__main__":
    main()
