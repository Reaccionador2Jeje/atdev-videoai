# AtDev VideoAI

**Open-source video creation and YouTube creator tools — with no credit system.**

AtDev VideoAI combines a code-driven video studio with creator research and channel optimization. It is designed to work both as an independent web application and through a future ChatGPT integration.

## Principles
- No credits, credit packs, or artificial generation tokens.
- Open source and community-driven.
- Local-first rendering wherever practical.
- AI providers and external APIs are optional, never required for the core editor.
- Hardware requirements, API quotas, and service limits are disclosed honestly.

## Current prototype
- Scene-based video editor with live preview.
- Landscape (16:9), portrait (9:16), and square (1:1) formats.
- Scene title, subtitle, background color, and duration controls.
- Add, select, and delete scenes.
- Export editable project data as JSON.
- Local Python rendering API powered by FFmpeg.
- MP4 export with text overlays and solid-color scene backgrounds.

## Run locally
Requirements: Python 3.9+ and FFmpeg installed and available on PATH.

Terminal 1, start the renderer:

    python engine/server.py

Terminal 2, serve the web app from the repository root:

    python -m http.server 8000

Open http://127.0.0.1:8000/editor.html.

See [engine/README.md](engine/README.md) for details.

## Planned modules
| Module | Purpose |
| --- | --- |
| Video Studio | Scene editing, timelines, captions, and compositions |
| Code Renderer | Export projects using FFmpeg |
| Creator Research | Organize video ideas, topics, and keywords |
| Channel Insights | Optional YouTube Data API integration |
| Thumbnail Studio | Compose thumbnail designs |
| ChatGPT Bridge | Expose project tools through an MCP-compatible server |

## Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License
This repository currently uses **CC0 1.0 Universal**. See [LICENSE](LICENSE).
