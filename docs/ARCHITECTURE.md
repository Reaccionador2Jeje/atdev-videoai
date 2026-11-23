# Architecture

## Product surfaces
1. **Web Studio:** standalone HTML/CSS/JavaScript editor.
2. **Local Render Engine:** Python API that invokes FFmpeg on the user's device.
3. **MCP Bridge:** stdio and authenticated HTTP transports for MCP-compatible clients, including supported ChatGPT MCP connection workflows.

## Current implementation
- Versioned project JSON with scene and audio-track data.
- Image assets embedded in project JSON and uploaded to the local renderer on explicit render.
- Video track composed from scenes; independent audio clips have start offsets and volume.
- FFmpeg scene rendering with text, imported images, zoom motion, fade-in and crossfade transitions.
- H.264/AAC MP4 output.
- Declarative JSON video generation; no arbitrary code execution.
- MCP tools for engine health, project creation, code-to-project generation, rendering and project listing.

## Local-first rules
- Core editor and renderer do not require an account, credits, or a paid AI provider.
- User media is not uploaded to third-party services by the application.
- External analytics and AI providers remain optional.
- The local render API binds to loopback by default.
- HTTP MCP refuses a public bind unless a sufficiently long bearer token is configured. Public deployment still requires HTTPS and appropriate reverse-proxy/security controls.

## Run
Start the renderer with `python engine/server.py`, serve the web files with `python -m http.server 8000`, then open `/editor.html`.

For MCP stdio, configure an MCP client to launch `python /absolute/path/to/atdev-videoai/mcp_server.py`.
For an HTTP MCP endpoint, start the renderer and then run `python mcp_http_server.py`. The endpoint is `http://127.0.0.1:8766/mcp`. For remote use, configure a secure HTTPS reverse proxy and set `ATDEV_MCP_HOST`, `ATDEV_MCP_TOKEN` (at least 24 characters), and `ATDEV_MCP_PORT`.

## MCP tools
- `videoai_health`
- `create_video_project`
- `create_video_from_code`
- `render_video_project`
- `list_video_projects`

## Roadmap
Creator research, keyword exploration, thumbnail composition, optional YouTube analytics, and richer visual/audio effects remain future modules.
