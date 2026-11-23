# AtDev VideoAI

**Open-source video creation and creator tools — with no credit system.**

AtDev VideoAI is both an independent web studio and an MCP-enabled video creation service. It uses your own device and FFmpeg to render videos locally.

## Implemented in this version
1. **Image import:** PNG, JPEG and WebP images can be assigned to scenes.
2. **Audio tracks:** import multiple audio clips, set each clip's timeline start and volume.
3. **Motion and transitions:** slow zoom-in, zoom-out, fade-in and per-scene cut/crossfade.
4. **Multitrack timeline:** visual video-scene lane plus independent audio lane and editable clip controls.
5. **Code video generation:** create complete editable projects from declarative JSON in the editor or through MCP. No arbitrary code is executed.
6. **ChatGPT MCP integration:** stateless Streamable HTTP MCP with OAuth 2.1 authorization-code + PKCE, dynamic client registration, per-tool scopes and refresh tokens.
7. **Signed MP4 delivery:** temporary HMAC-signed HTTPS download links for rendered videos.

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

For ChatGPT-specific setup, account availability, protocol details and security notes, see [docs/CHATGPT.md](docs/CHATGPT.md). The HTTP endpoint implements stateless Streamable HTTP MCP over JSON. ChatGPT custom-app availability depends on the plan and workspace; this repository cannot enable account features.

See [ChatGPT integration guide](docs/CHATGPT.md), [engine/README.md](engine/README.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Principles
- No credits, credit packs, or artificial generation tokens.
- Open source and community-driven.
- Local-first rendering.
- No automatic upload of user media to third-party services.
- Hardware requirements and external API limits are disclosed honestly.

## License
This repository currently uses **CC0 1.0 Universal**. See [LICENSE](LICENSE).
