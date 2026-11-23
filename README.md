# AtDev VideoAI

**Open-source video creation and creator tools — with no credit system.**

AtDev VideoAI is both an independent web studio and an MCP-enabled video creation service. It uses your own device and FFmpeg to render videos locally.

## Implemented in this version
1. **Image import:** PNG, JPEG and WebP images can be assigned to scenes.
2. **Audio tracks:** import multiple audio clips, set each clip's timeline start and volume.
3. **Motion and transitions:** slow zoom-in, zoom-out, fade-in and per-scene cut/crossfade.
4. **Multitrack timeline:** visual video-scene lane plus independent audio lane and editable clip controls.
5. **Code video generation:** create complete editable projects from declarative JSON in the editor or through MCP. No arbitrary code is executed.
6. **MCP integration:** stdio and authenticated HTTP MCP servers expose project creation, code generation, project listing, engine health and MP4 rendering.

The renderer exports H.264/AAC MP4 using FFmpeg. No paid API or cloud credit system is required.

## Run the web studio locally
Requirements: Python 3.9+ and FFmpeg available on PATH.

Terminal 1:

    python engine/server.py

Terminal 2, from the repository root:

    python -m http.server 8000

Open http://127.0.0.1:8000/editor.html.

## Connect an MCP client
Start the render engine first. Configure your MCP-compatible client to launch:

    python /absolute/path/to/atdev-videoai/mcp_server.py

The stdio bridge exposes:
- `videoai_health`
- `create_video_project`
- `create_video_from_code`
- `render_video_project`
- `list_video_projects`

For an HTTP MCP endpoint, start:

    python mcp_http_server.py

Local endpoint: http://127.0.0.1:8766/mcp

For remote ChatGPT MCP connections, deploy behind HTTPS and set `ATDEV_MCP_HOST` and a random `ATDEV_MCP_TOKEN` of at least 24 characters. The HTTP server refuses a non-loopback bind without that token. Configure the remote MCP URL and bearer token in a ChatGPT MCP-capable connection/client. Availability of remote MCP connections depends on the ChatGPT workspace and account configuration; the local stdio bridge is for compatible desktop MCP clients.

See [engine/README.md](engine/README.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Principles
- No credits, credit packs, or artificial generation tokens.
- Open source and community-driven.
- Local-first rendering.
- No automatic upload of user media to third-party services.
- Hardware requirements and external API limits are disclosed honestly.

## License
This repository currently uses **CC0 1.0 Universal**. See [LICENSE](LICENSE).
