"""
Gate 3 - table-aware DATE_COLUMN capability.

WHAT THIS ADDS

TimeStrategyResolver._discover_capability() deliberately leaves
TimeCapability.date_columns empty, documented there as: TimeCapability is
scoped to a CONNECTION while semantic_table_config's temporal_strategy is
scoped to a TABLE, so publishing one table's date column on the
connection-wide capability would offer it for a query against a different
table entirely. That reasoning is sound and is left untouched here - the
connection-wide discovery still returns no date columns.

This module answers the question that reasoning leaves open: once a
specific table IS known (a metric already resolved, or a caller otherwise
has one in hand), what is ITS configured date column? Same shape and same
safety rules as SnapshotConfigLoader.for_table() (Gate 3 Step 7a):

  - cache keyed on (connection_id, table_name)
  - no TOP 1 / ORDER BY - one confirmed row per table
  - is_confirmed = 1 only
  - NOT combined with the legacy/connection-wide behaviour - an
    unconfigured or unconfirmed table comes back unconfigured, never a
    guess

CONFIGURED VALUE VALIDATION

semantic_table_config.month_column is administrator-entered free text and
is reused here as "the date column" for a DATE_COLUMN-strategy table - the
same field SnapshotConfigLoader reads for a SNAPSHOT table's month
grouping. One confirmed row on the live connection holds
"Docdate (YYYY-MM-DD)" for a DATE_COLUMN table, which is a display format,
not a column name. Reusing SemanticPlanBuilder._registered_dimension() -
the same check Gate 3 Step 7b already applies to month_column - is what
keeps that row from being planned onto a column that does not exist: a
configured value that is not a real, registered, active dimension column on
THIS table comes back unconfigured rather than being trusted.

WHAT THIS DOES NOT DO

It does not change TimeStrategyResolver, TemporalPipeline's call order, or
which strategy TimeStrategySelector picks - TemporalPipeline still runs
before a metric table is known, exactly as before. It is an additive
building block for a caller that already knows the table (mirroring how
semantic_resolver.py / semantic_plan_builder.py use
SnapshotConfigLoader.for_table() once THEY know the table) to build a
table-aware TimeCapability for it; see
TimeStrategyResolver.discover_capability_for_table().
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300


@dataclass
class DateColumnConfig:
    """The DATE_COLUMN configuration of one table, or the unconfigured default."""

    table_name: Optional[str] = None
    date_column: Optional[str] = None
    is_configured: bool = False


class DateColumnConfigLoader:
    """Reads and caches one table's DATE_COLUMN configuration."""

    _lock = threading.Lock()
    _cache: Dict[tuple, tuple] = {}  # (connection_id, table_name) -> (loaded_at, DateColumnConfig)

    @classmethod
    def invalidate(cls, connection_id: Optional[str] = None) -> None:
        """Drop cached configuration. Called when an administrator saves."""
        with cls._lock:
            if connection_id is None:
                cls._cache.clear()
            else:
                for key in [k for k in cls._cache if k[0] == connection_id]:
                    cls._cache.pop(key, None)

    @classmethod
    def for_table(
        cls,
        connection_id: Optional[str],
        table_name: Optional[str],
    ) -> DateColumnConfig:
        """
        The DATE_COLUMN configuration of ONE named table.

        Never raises: a caller that cannot read configuration must still be
        able to proceed treating the table as unconfigured, the same
        contract SnapshotConfigLoader.for_table() and for_connection() both
        keep.
        """
        if not connection_id or not table_name:
            return DateColumnConfig()

        key = (connection_id, table_name)

        with cls._lock:
            cached = cls._cache.get(key)
            if cached and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        try:
            config = cls._load(connection_id, table_name)
        except Exception as exc:
            logger.warning(
                "Could not read DATE_COLUMN configuration for %s on %s (%s); "
                "treating the table as unconfigured.",
                table_name, connection_id, exc,
            )
            return DateColumnConfig()

        with cls._lock:
            cls._cache[key] = (time.time(), config)

        return config

    @classmethod
    def _load(cls, connection_id: str, table_name: str) -> DateColumnConfig:
        # Imported here, not at module scope: this module is pulled in by
        # the temporal package, which the test suite imports without a
        # database - see snapshot_config.py's identical note.
        from database import engine

        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT table_name, month_column
                FROM semantic_table_config
                WHERE connection_id = :connection_id
                  AND table_name = :table_name
                  AND temporal_strategy = 'DATE_COLUMN'
                  AND is_confirmed = 1
            """), {
                "connection_id": connection_id,
                "table_name": table_name,
            }).fetchone()

        if not row or not row[1]:
            return DateColumnConfig()

        configured_column = row[1]

        # Free text, validated against the real schema - see the module
        # docstring's CONFIGURED VALUE VALIDATION section.
        from semantic.semantic_plan_builder import SemanticPlanBuilder

        registered = SemanticPlanBuilder._registered_dimension(
            connection_id, table_name, configured_column
        )
        if not registered:
            return DateColumnConfig()

        return DateColumnConfig(
            table_name=row[0],
            date_column=registered["column_name"],
            is_configured=True,
        )
