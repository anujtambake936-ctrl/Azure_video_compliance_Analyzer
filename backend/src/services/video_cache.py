"""Simple cache for Azure Video Indexer results to avoid re-processing the same video."""
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("video-cache")

CACHE_DIR = Path("backend/cache/video_indexer")


def _get_cache_key(video_url: str, mode: str = "full") -> str:
    """Generate a stable cache key from video URL."""
    cache_input = f"v2:{mode}:{video_url}"
    return hashlib.sha256(cache_input.encode()).hexdigest()[:16]


def get_cached_result(video_url: str, mode: str = "full") -> Optional[Dict[str, Any]]:
    """Retrieve cached video indexer result if it exists."""
    cache_key = _get_cache_key(video_url, mode)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Cache HIT for {video_url[:50]}... (key: {cache_key})")
            return data
    except Exception as e:
        logger.warning(f"Failed to read cache file {cache_file}: {e}")
        return None


def save_to_cache(video_url: str, result: Dict[str, Any], mode: str = "full") -> None:
    """Save video indexer result to cache."""
    cache_key = _get_cache_key(video_url, mode)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CACHE_DIR, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(result, temp_file, indent=2)
        os.replace(temp_path, cache_file)
        logger.info(f"Saved cache for {video_url[:50]}... (key: {cache_key})")
    except Exception as e:
        logger.warning(f"Failed to save cache to {cache_file}: {e}")


def clear_cache(video_url: Optional[str] = None) -> int:
    """Clear cache for a specific video or all cached videos."""
    if video_url:
        cache_key = _get_cache_key(video_url)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            cache_file.unlink()
            return 1
        return 0
    else:
        # Clear all
        if not CACHE_DIR.exists():
            return 0
        count = 0
        for cache_file in CACHE_DIR.glob("*.json"):
            cache_file.unlink()
            count += 1
        return count
