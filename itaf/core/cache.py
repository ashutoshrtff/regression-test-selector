#!/usr/bin/env python3
"""
itaf.core.cache - Incremental Processing and Artifact Hash Cache.

Provides token and processing efficiency by computing SHA-256 hashes of input
specifications and automation files. Avoids repeatedly re-parsing unchanged artifacts.
Standard library only.
"""

import hashlib
import os
from typing import Any, Callable, Dict, Optional, Tuple


def compute_file_hash(filepath: str) -> str:
    """Computes SHA-256 hash of a file's contents."""
    if not os.path.exists(filepath):
        return ""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class ArtifactCache:
    """In-memory cache keyed by (filepath, sha256_hash)."""

    def __init__(self):
        self._cache: Dict[str, Tuple[str, Any]] = {}

    def get(self, filepath: str) -> Optional[Any]:
        """Returns cached parsed object if file exists and hash matches."""
        abs_path = os.path.abspath(filepath)
        if abs_path not in self._cache:
            return None
        cached_hash, cached_obj = self._cache[abs_path]
        current_hash = compute_file_hash(abs_path)
        if current_hash and current_hash == cached_hash:
            return cached_obj
        # Stale entry - invalidate
        del self._cache[abs_path]
        return None

    def put(self, filepath: str, obj: Any) -> None:
        """Stores parsed object with the file's current SHA-256 hash."""
        abs_path = os.path.abspath(filepath)
        current_hash = compute_file_hash(abs_path)
        if current_hash:
            self._cache[abs_path] = (current_hash, obj)

    def invalidate(self, filepath: Optional[str] = None) -> None:
        """Invalidates a single file or entire cache."""
        if filepath:
            abs_path = os.path.abspath(filepath)
            self._cache.pop(abs_path, None)
        else:
            self._cache.clear()

    def get_or_compute(self, filepath: str, compute_fn: Callable[[], Any]) -> Any:
        """Returns cached value if valid, otherwise computes and stores."""
        cached = self.get(filepath)
        if cached is not None:
            return cached
        result = compute_fn()
        self.put(filepath, result)
        return result


# Global singleton cache instance for the process
GLOBAL_ARTIFACT_CACHE = ArtifactCache()
