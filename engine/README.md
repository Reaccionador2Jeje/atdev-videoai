# AtDev VideoAI local render engine

## Requirements
- Python 3.9+
- FFmpeg with libx264, AAC, drawtext and xfade support, available on PATH.

## Start the engine
From the repository root:

    python engine/server.py

Keep the terminal open. The local API listens on http://127.0.0.1:8765.

In another terminal, serve the web app:

    python -m http.server 8000

Open http://127.0.0.1:8000/editor.html.

## Implemented rendering features
- Landscape 16:9, portrait 9:16 and square 1:1 output.
- Per-scene solid background, title and subtitle.
- PNG, JPEG and WebP scene image imports.
- Multiple audio clips, each with a start offset and volume.
- Slow zoom-in, zoom-out and fade-in scene motion.
- Per-scene cut or crossfade transition.
- MP4 output with H.264 video and AAC audio.
- 30 fps local rendering; no cloud credits or external AI provider.

The editor embeds imported media in the downloadable project JSON and sends it to the local engine only when the user chooses Render. The engine stores imported assets under engine/assets/ and rendered videos under engine/renders/. These folders are generated locally and should not be committed.

## API
- GET /api/health — reports FFmpeg availability.
- POST /api/render — accepts project JSON including scenes, audioTracks and data-URL assets.
- GET /renders/<filename>.mp4 — serves a rendered video.

## Limits
- Up to 30 scenes and 20 audio clips per project.
- Image files: 12 MB each; audio files: 25 MB each.
- Render requests: 50 MB maximum.
- Supported audio: MP3, WAV, M4A, AAC, OGG, WebM and FLAC.

## Security
The renderer binds to 127.0.0.1 only. Do not expose it to the public internet. The editor sends media to this local server only when rendering.
