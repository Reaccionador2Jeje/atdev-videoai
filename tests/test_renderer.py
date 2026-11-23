import base64
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("atdev_engine", ROOT / "engine" / "server.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for renderer integration test")
class RenderSmokeTest(unittest.TestCase):
    def test_image_audio_motion_and_crossfade_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "sample.png"
            audio = Path(tmp) / "sample.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=c=blue:s=320x180", "-frames:v", "1", str(image)], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=3", str(audio)], check=True)
            image_data = base64.b64encode(image.read_bytes()).decode()
            audio_data = base64.b64encode(audio.read_bytes()).decode()
            project = {
                "version": 2, "name": "CI render smoke test", "format": "16:9",
                "scenes": [
                    {"title": "First scene", "subtitle": "Image + zoom", "background": "#18221d",
                     "duration": 2, "animation": "zoom-in", "transition": "fade", "image": "img1"},
                    {"title": "Second scene", "subtitle": "Fade in", "background": "#243047",
                     "duration": 2, "animation": "fade-in", "transition": "cut"}
                ],
                "audioTracks": [{"asset": "aud1", "start": 0, "volume": 0.35}],
                "assets": {
                    "img1": {"name": "sample.png", "mime": "image/png", "data": "data:image/png;base64," + image_data},
                    "aud1": {"name": "sample.wav", "mime": "audio/wav", "data": "data:audio/wav;base64," + audio_data}
                }
            }
            filename = engine.render(project)
            output = engine.OUT / filename
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1000)
            output.unlink()

if __name__ == "__main__":
    unittest.main()
