#!/usr/bin/env python3
"""Minimal dependency-free MCP stdio bridge for AtDev VideoAI."""
import json
import sys
import urllib.request
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"
PROJECTS.mkdir(exist_ok=True)
ENGINE = "http://127.0.0.1:8765"

TOOLS = [
    {"name": "videoai_health", "description": "Check whether the local AtDev VideoAI FFmpeg render engine is running.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "create_video_project", "description": "Create and save an editable AtDev VideoAI project from structured scene data. No credits or external AI provider required.",
     "inputSchema": {"type": "object", "properties": {"project": {"type": "object", "description": "Project JSON with name, format, scenes and optional audioTracks/assets."}}, "required": ["project"], "additionalProperties": False}},
    {"name": "create_video_from_code", "description": "Generate an editable project from declarative JSON text. This is data, not executable Python or JavaScript.",
     "inputSchema": {"type": "object", "properties": {"project_json": {"type": "string", "description": "JSON project definition with scenes."}, "render": {"type": "boolean", "description": "Render an MP4 immediately if true."}}, "required": ["project_json"], "additionalProperties": False}},
    {"name": "render_video_project", "description": "Render a previously saved project ID to MP4 using the local FFmpeg engine.",
     "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"], "additionalProperties": False}},
    {"name": "list_video_projects", "description": "List saved AtDev VideoAI project IDs and names.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}
]

def call_engine(project):
    body = json.dumps(project).encode()
    request = urllib.request.Request(ENGINE + "/api/render", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode())
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
