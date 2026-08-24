import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.src.api.server import AuditRequest
from backend.src.services.video_cache import get_cached_result, save_to_cache
from backend.src.services.video_indexer import is_youtube_url
from backend.src.services.report_store import (
    delete_report,
    get_report,
    list_reports,
    save_report,
)


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

    def test_api_request_accepts_processing_mode(self):
        request = AuditRequest(
            video_url="https://youtu.be/video-id", processing_mode="fast"
        )
        self.assertEqual(request.processing_mode, "fast")

    def test_report_store_persists_and_deletes_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "backend.src.services.report_store.REPORTS_DIR", Path(directory)
            ):
                report = {
                    "session_id": "job-123",
                    "status": "PASS",
                    "completed_at": "2026-08-24T12:00:00",
                }
                save_report("job-123", report)

                self.assertEqual(get_report("job-123"), report)
                self.assertEqual(list_reports(), [report])
                self.assertTrue(delete_report("job-123"))
                self.assertIsNone(get_report("job-123"))


if __name__ == "__main__":
    unittest.main()