from typing import List, Optional
from semantic.matching.models import CachedDimensionValue

class DimensionValueCache:
    """
    Dedicated in-memory cache service for preprocessed dimension values
    supporting version-based invalidation.
    """
    def __init__(self):
        self._cache = {}      # (connection_id, version) -> List[CachedDimensionValue]
        self._versions = {}   # connection_id -> int

    def _get_cache_key(self, connection_id: str) -> tuple:
        version = self._versions.setdefault(connection_id, 1)
        return (connection_id, version)

    def get(self, connection_id: str) -> Optional[List[CachedDimensionValue]]:
        key = self._get_cache_key(connection_id)
        return self._cache.get(key)

    def put(self, connection_id: str, values: List[CachedDimensionValue]):
        key = self._get_cache_key(connection_id)
        self._cache[key] = values

    def invalidate(self, connection_id: str):
        """
        Increments the version of the connection, rendering all previous
        cached entries obsolete.
        """
        self._versions[connection_id] = self._versions.get(connection_id, 1) + 1

    def clear(self):
        """
        Clears all cached values and resets version numbers.
        """
        self._cache.clear()
        self._versions.clear()
