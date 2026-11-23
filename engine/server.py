#!/usr/bin/env python3
"""Local AtDev VideoAI renderer with images, audio, motion and transitions."""
import base64, json, os, re, shutil, subprocess, tempfile, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "renders"
ASSETS = ROOT / "assets"
OUT.mkdir(exist_ok=True)
ASSETS.mkdir(exist_ok=True)
PORT = int(os.environ.get("ATDEV_PORT", "8765"))
FORMATS = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (720, 720)}
MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
            "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav",
            "audio/x-wav": ".wav", "audio/mp4": ".m4a", "audio/aac": ".aac",
            "audio/ogg": ".ogg", "audio/webm": ".webm", "audio/flac": ".flac"}

def run(cmd, timeout=240):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr[-1800:] or "FFmpeg failed.")
    return result

def save_assets(raw_assets):
    saved = {}
    if not isinstance(raw_assets, dict) or len(raw_assets) > 60:
        raise ValueError("Assets must be an object with at most 60 files.")
    for key, item in raw_assets.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", str(key)) or not isinstance(item, dict):
            raise ValueError("Invalid asset identifier.")
        mime = item.get("mime", "")
        if mime not in MIME_EXT:
            raise ValueError("Unsupported media type: " + str(mime))
        data = item.get("data", "")
        if not isinstance(data, str) or "," not in data:
            raise ValueError("Invalid data URL for asset " + str(key))
        payload = data.split(",", 1)[1]
        try:
            binary = base64.b64decode(payload, validate=True)
        except Exception:
            raise ValueError("Invalid base64 media data.")
        limit = 12 * 1024 * 1024 if mime.startswith("image/") else 25 * 1024 * 1024
        if len(binary) > limit:
            raise ValueError("Media file exceeds the per-file size limit.")
        filename = "asset-" + uuid.uuid4().hex + MIME_EXT[mime]
        path = ASSETS / filename
        path.write_bytes(binary)
        saved[key] = path
    return saved

def render(project):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed or not on PATH.")
    scenes = project.get("scenes")
    if not isinstance(scenes, list) or not scenes or len(scenes) > 30:
        raise ValueError("Add between 1 and 30 scenes.")
    fmt = project.get("format", "16:9")
    if fmt not in FORMATS:
        raise ValueError("Invalid video format.")
    assets = save_assets(project.get("assets", {}))
    width, height = FORMATS[fmt]
    with tempfile.TemporaryDirectory(prefix="atdev-videoai-") as temp:
        tempdir = Path(temp)
        segments = []
        durations = []
        for index, scene in enumerate(scenes):
            duration = max(1.0, min(30.0, float(scene.get("duration", 5))))
            durations.append(duration)
            background = scene.get("background", "#18221d")
            if not isinstance(background, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", background):
                background = "#18221d"
            args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i",
                    "color=c=" + background + ":s=" + str(width) + "x" + str(height) + ":r=30:d=" + str(duration)]
            image_key = scene.get("image")
            image_path = assets.get(image_key)
            if image_path:
                args += ["-loop", "1", "-t", str(duration), "-i", str(image_path)]
            filters = []
            if image_path:
                filters.append("[1:v]scale=" + str(width) + ":" + str(height) +
                    ":force_original_aspect_ratio=decrease,pad=" + str(width) + ":" + str(height) +
                    ":(ow-iw)/2:(oh-ih)/2,setsar=1[img]")
                filters.append("[0:v][img]overlay=0:0:shortest=1[base]")
                base = "[base]"
            else:
                base = "[0:v]"
            animation = scene.get("animation", "none")
            if animation == "zoom-in":
                filters.append(base + "zoompan=z='min(zoom+0.0008,1.12)':d=1:s=" + str(width) + "x" + str(height) + ":fps=30[motion]")
                base = "[motion]"
            elif animation == "zoom-out":
                filters.append(base + "zoompan=z='if(eq(on,1),1.12,max(1.0,zoom-0.0008))':d=1:s=" + str(width) + "x" + str(height) + ":fps=30[motion]")
                base = "[motion]"
            elif animation == "fade-in":
                filters.append(base + "fade=t=in:st=0:d=0.8[motion]")
                base = "[motion]"
            for key, text_value, y, size in [
                ("title", scene.get("title", ""), "h*0.39", max(26, width // 22)),
                ("subtitle", scene.get("subtitle", ""), "h*0.56", max(16, width // 42))]:
                if text_value:
                    textfile = tempdir / (str(index) + "-" + key + ".txt")
                    textfile.write_text(str(text_value)[:180].replace("\x00", ""), encoding="utf-8")
                    path_value = str(textfile).replace("\\", "/")
                    filters.append(base + "drawtext=textfile='" + path_value + "':fontcolor=" +
                        ("white" if key == "title" else "0xD5DEC9") + ":fontsize=" + str(size) +
                        ":x=(w-text_w)/2:y=" + y + "[txt" + str(index) + key + "]")
                    base = "[txt" + str(index) + key + "]"
            filters.append(base + "format=yuv420p[vout]")
            output = tempdir / ("segment-" + str(index) + ".mp4")
            args += ["-filter_complex", ";".join(filters), "-map", "[vout]",
                     "-an", "-c:v", "libx264", "-preset", "ultrafast", "-r", "30",
                     "-pix_fmt", "yuv420p", str(output)]
            run(args)
            segments.append(output)

        # Join scenes. A fade transition uses xfade; a cut uses a 1ms crossfade.
        final_video = tempdir / "video-only.mp4"
        if len(segments) == 1:
            shutil.copyfile(segments[0], final_video)
        else:
            inputs = []
            for segment in segments:
                inputs += ["-i", str(segment)]
            graph = []
            for i in range(len(segments)):
                graph.append("[" + str(i) + ":v]settb=AVTB,setpts=PTS-STARTPTS[v" + str(i) + "]")
            previous = "[v0]"
            elapsed = durations[0]
            for i in range(1, len(segments)):
                fade = scenes[i-1].get("transition") == "fade"
                cross = 0.6 if fade else 0.001
                offset = max(0.0, elapsed - cross)
                out_label = "[mix" + str(i) + "]"
                graph.append(previous + "[v" + str(i) + "]xfade=transition=fade:duration=" +
                             str(cross) + ":offset=" + str(offset) + out_label)
                previous = out_label
                elapsed += durations[i] - cross
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + inputs +
                ["-filter_complex", ";".join(graph), "-map", previous, "-an",
                 "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(final_video)])

        # Audio clips are independent timeline tracks; each can start later and have its own gain.
        audio_inputs = []
        audio_filters = []
        for clip in project.get("audioTracks", [])[:20]:
            key = clip.get("asset")
            path = assets.get(key)
            if not path or not path.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm", ".flac"}:
                continue
            audio_inputs += ["-i", str(path)]
            idx = len(audio_inputs) // 2 - 1
            start_ms = max(0, min(3600000, int(float(clip.get("start", 0)) * 1000)))
            volume = max(0.0, min(2.0, float(clip.get("volume", 1))))
            audio_filters.append("[" + str(idx + 1) + ":a]asetpts=PTS-STARTPTS,volume=" +
                str(volume) + ",adelay=" + str(start_ms) + "|" + str(start_ms) + "[a" + str(idx) + "]")
        filename = "video-" + uuid.uuid4().hex[:12] + ".mp4"
        destination = OUT / filename
        if audio_filters:
            labels = "".join("[a" + str(i) + "]" for i in range(len(audio_filters)))
            audio_filters.append(labels + "amix=inputs=" + str(len(audio_filters)) + ":duration=longest:dropout_transition=0[aout]")
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(final_video)] +
                audio_inputs + ["-filter_complex", ";".join(audio_filters), "-map", "0:v", "-map", "[aout]",
                "-t", str(sum(durations)), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destination)])
        else:
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(final_video),
                 "-c", "copy", "-movflags", "+faststart", str(destination)])
    return filename

class API(BaseHTTPRequestHandler):
    def reply(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)
    def do_OPTIONS(self):
        self.reply(200, {"ok": True})
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self.reply(200, {"ok": True, "ffmpeg": bool(shutil.which("ffmpeg"))})
            return
        if path.startswith("/renders/"):
            name = Path(path).name
            if not re.fullmatch(r"video-[a-f0-9]+\.mp4", name):
                self.send_error(404)
                return
            file = OUT / name
            if not file.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file.stat().st_size))
            self.end_headers()
            with file.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)
            return
        self.reply(404, {"error": "Not found"})
    def do_POST(self):
        if urlparse(self.path).path != "/api/render":
            self.reply(404, {"error": "Not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 50 * 1024 * 1024:
                raise ValueError("Project request must be at most 50 MB.")
            project = json.loads(self.rfile.read(size))
            filename = render(project)
            self.reply(200, {"ok": True, "filename": filename,
                "url": "http://127.0.0.1:" + str(PORT) + "/renders/" + filename})
        except subprocess.TimeoutExpired:
            self.reply(504, {"error": "Render timed out. Try shorter scenes or smaller media."})
        except Exception as error:
            self.reply(400, {"error": str(error)})
    def log_message(self, *args):
        pass

if __name__ == "__main__":
    print("AtDev VideoAI renderer: http://127.0.0.1:" + str(PORT))
    print("FFmpeg: " + str(bool(shutil.which("ffmpeg"))))
    ThreadingHTTPServer(("127.0.0.1", PORT), API).serve_forever()
