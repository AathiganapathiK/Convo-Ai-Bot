from dataclasses import dataclass, field
import datetime
from typing import Optional, Dict
from .models import TimeCapability
from .enums import TimeStrategyType, TimeIntentType

@dataclass
class CapabilityCacheEntry:
    """Represents a cached capability entry for a database connection."""
    connection_id: str
    capability: TimeCapability
    preferred_strategy: Optional[TimeStrategyType]
    created_at: datetime.datetime
    last_accessed: datetime.datetime
    strategy_selections: Dict[TimeIntentType, TimeStrategyType] = field(default_factory=dict)


class TimeResolutionCache:
    """Thread-safe, process-level cache for database temporal capabilities and strategies."""
    _cache: Dict[str, CapabilityCacheEntry] = {}

    @classmethod
    def get(cls, connection_id: str) -> Optional[CapabilityCacheEntry]:
        """Retrieve a cache entry and update its last accessed timestamp."""
        entry = cls._cache.get(connection_id)
        if entry:
            entry.last_accessed = datetime.datetime.now()
        return entry

    @classmethod
    def put(
        cls,
        connection_id: str,
        capability: TimeCapability,
        preferred_strategy: Optional[TimeStrategyType] = None
    ) -> CapabilityCacheEntry:
        """Store or update a cache entry with the connection's capability and strategy."""
        now = datetime.datetime.now()
        existing = cls._cache.get(connection_id)
        strategy_selections = existing.strategy_selections if existing else {}
        entry = CapabilityCacheEntry(
            connection_id=connection_id,
            capability=capability,
            preferred_strategy=preferred_strategy,
            created_at=now,
            last_accessed=now,
            strategy_selections=strategy_selections
        )
        cls._cache[connection_id] = entry
        return entry

    @classmethod
    def invalidate(cls, connection_id: Optional[str]) -> None:
        """Evict a specific connection's entry from the cache safely."""
        if connection_id and connection_id in cls._cache:
            del cls._cache[connection_id]

    @classmethod
    def clear(cls) -> None:
        """Clear all entries in the cache."""
        cls._cache.clear()
