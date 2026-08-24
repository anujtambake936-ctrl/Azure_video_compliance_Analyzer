import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.src.api.server import AuditRequest
from backend.src.services.video_cache import get_cached_result, save_to_cache
from backend.src.services.video_indexer import is_youtube_url


class RegressionTests(unittest.TestCase):
    def test_youtube_validation_requires_exact_hostname(self):
        self.assertTrue(is_youtube_url("https://youtu.be/video-id"))
        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=video-id"))
        self.assertFalse(is_youtube_url("https://example.com/youtube.com/video"))
        self.assertFalse(is_youtube_url("ftp://youtu.be/video-id"))

    def test_cache_isolated_by_processing_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "backend.src.services.video_cache.CACHE_DIR", Path(directory)
            ):
                url = "https://youtu.be/video-id"
                save_to_cache(url, {"mode": "full"}, mode="full")
                save_to_cache(url, {"mode": "fast"}, mode="fast")

                self.assertEqual(get_cached_result(url, mode="full"), {"mode": "full"})
                self.assertEqual(get_cached_result(url, mode="fast"), {"mode": "fast"})

    def test_api_request_rejects_non_http_url(self):
        with self.assertRaises(ValueError):
            AuditRequest(video_url="file:///tmp/video.mp4")


if __name__ == "__main__":
    unittest.main()