# Local render engine

Requirements: Python 3.9+ and FFmpeg installed and available on PATH.

From the repository root, start the API:

    python engine/server.py

Keep that terminal open. The API listens on http://127.0.0.1:8765.

In another terminal, serve the web files:

    python -m http.server 8000

Open http://127.0.0.1:8000/editor.html.

API endpoints:
- GET /api/health checks whether FFmpeg is available.
- POST /api/render accepts a project JSON with format and scenes.
- GET /renders/filename.mp4 serves the rendered video.

The first renderer supports solid-color backgrounds and text overlays. Images, audio, transitions, and animation tracks are planned next.

The server binds to loopback only. Do not expose it to the public internet. Rendered videos are stored in engine/renders/ and should not be committed.
