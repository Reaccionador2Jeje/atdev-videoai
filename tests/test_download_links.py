import hashlib
import hmac
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import mcp_server


class SignedDownloadTests(unittest.TestCase):
    def test_signed_url_uses_expiring_hmac_and_https(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rendered = root / "engine" / "renders"
            rendered.mkdir(parents=True)
            filename = "video-0123456789ab.mp4"
            (rendered / filename).write_bytes(b"test mp4")
            with patch.object(mcp_server, "ROOT", root), patch.dict(os.environ, {
                "ATDEV_PUBLIC_BASE_URL": "https://video.example.test",
                "ATDEV_DOWNLOAD_SECRET": "s" * 48,
            }):
                url = mcp_server.signed_download_url(filename)
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            expires = int(query["expires"][0])
            expected = hmac.new(
                ("s" * 48).encode(),
                (filename + ":" + str(expires)).encode(),
                hashlib.sha256,
            ).hexdigest()
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.path, "/download/" + filename)
            self.assertEqual(query["sig"][0], expected)
            self.assertGreater(expires, 0)

    def test_rejects_untrusted_filename(self):
        with self.assertRaises(ValueError):
            mcp_server.signed_download_url("../private.txt")


if __name__ == "__main__":
    unittest.main()
