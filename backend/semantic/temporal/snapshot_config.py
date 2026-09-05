"""
Gate 2 Step 11a - the configured snapshot bindings, read from the database.

WHAT THIS REPLACES
------------------
SNAPSHOT_SALES_BINDINGS, a five-entry dictionary in semantic_plan_builder.py
that hardcoded one customer's column names into the query planner, alongside a
hardcoded table name and a hardcoded set of measure columns. Those now come
from semantic_table_config and semantic_snapshot_mapping, written by
tools/seed_semantic_config.py.

WHAT IT DELIBERATELY DOES NOT DO YET
------------------------------------
It exposes period_scope on every binding, but nothing selects on it yet.
Choosing PYTD over PY for a year-on-year comparison is Step 11b, and it changes
reported figures, so it is a separate decision. Until then the flat mapping
resolves exactly as the old dictionary did: FULL for a prior year, and the
current year's only column for offset 0.

THE LEGACY DEFAULT
------------------
DEFAULT_BINDINGS below is the old dictionary, kept in this one place and used
only when a caller has no connection or the connection has no configuration -
which is the case in the unit tests, and on any environment where Step 13 has
not been run. It is not a silent fallback: every use logs, and callers surface
it as an assumption on the plan. Delete it once every environment is
configured and the tests inject configuration of their own.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from sqlalchemy import text

logger = logging.getLogger(__name__)


# The pre-configuration behaviour, preserved exactly: offset -> column, VALUE
# measures only, full prior years. See the module docstring before using it.
DEFAULT_BINDINGS: Dict[int, str] = {
    0: "CY",
    1: "PY",
    2: "PPY",
    3: "PPPY",
    4: "PPPPY",
}

DEFAULT_TABLE = "QB_MDJMD_SALES_5YRS_SUMMARY"

DEFAULT_MEASURE_COLUMNS = {
    "CY", "PY", "PPY", "PPPY", "PPPPY",
    "CYQ", "PYQ", "PPYQ", "PPPYQ", "PPPPYQ",
}

# How long a loaded configuration is reused before it is read again. The plan
# builder runs on every question, so this cannot be a database round trip each
# time; an administrator's save calls invalidate() directly, so the window only
# matters for a change made outside the application.
CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class SnapshotBinding:
    """One configured column: which period, which kind of measure, which span."""

    period_offset: int
    measure_kind: str      # VALUE | QUANTITY
    period_scope: str      # FULL | TO_DATE
    column_name: str


@dataclass
class SnapshotConfig:
    """
    The snapshot configuration for one connection.

    `is_configured` is False when this was assembled from DEFAULT_BINDINGS, so a
    caller can say so rather than presenting a guess as configuration.
    """

    table_name: Optional[str] = None
    bindings: List[SnapshotBinding] = field(default_factory=list)
    month_column: Optional[str] = None
    month_sort_column: Optional[str] = None
    fiscal_year_start_month: int = 4
    is_configured: bool = False

    # ------------------------------------------------------------------
    # What callers actually ask
    # ------------------------------------------------------------------

    @property
    def measure_columns(self) -> Set[str]:
        """Every column bound to a period, of either measure kind."""
        return {b.column_name for b in self.bindings}

    def column_for(self, period_offset: int, measure_kind: str = "VALUE",
                   scope: Optional[str] = None) -> Optional[str]:
        """
        The single configured column for one period, or None.

        `scope` may be given explicitly ("TO_DATE" for a till-date question).
        Left unset, it takes the natural reading: the running period is always
        to-date because it cannot be anything else, and a past period means the
        complete year unless the question said otherwise. Falls back to the
        other scope rather than returning nothing, since a configuration that
        binds only one of the two still answers the question - the caller can
        see which column came back and say what it covers.
        """
        candidates = [b for b in self.bindings
                      if b.period_offset == period_offset
                      and b.measure_kind == measure_kind]
        if not candidates:
            return None

        wanted = scope or ("TO_DATE" if period_offset == 0 else "FULL")
        for binding in candidates:
            if binding.period_scope == wanted:
                return binding.column_name

        return candidates[0].column_name

    @property
    def resolvable_columns(self) -> Set[str]:
        """
        The columns the period resolution can actually produce today.

        Narrower than measure_columns, and deliberately so. A caller uses this
        to decide "does this metric need its period chosen for it?", and
        answering yes for a column the resolver cannot return means the
        explicit column is captured and then replaced by a different one.

        PYTD is the live example: it is a configured binding, so it is in
        measure_columns, but nothing requests TO_DATE until Step 11b, so the
        resolver can never produce it. Claiming it here would turn a question
        that correctly found PYTD into one answered with PY.
        """
        return set(self.offset_to_column("VALUE").values()) | set(
            self.offset_to_column("QUANTITY").values()
        )

    def column_for_offset(
        self,
        period_offset: int,
        measure_kind: str = "VALUE",
        period_scope: Optional[str] = None,
    ) -> Optional[str]:
        """
        The column for one period.

        With no period_scope given, FULL wins and TO_DATE is the fallback. That
        is the pre-Step-11 behaviour and it is right for a plain "last year's
        sales", which means the whole year. It is NOT right for a comparison
        against a part-finished current year - that is Step 11b's problem, and
        it will ask for TO_DATE explicitly.
        """
        matches = [
            b for b in self.bindings
            if b.period_offset == period_offset and b.measure_kind == measure_kind
        ]

        if not matches:
            return None

        if period_scope:
            exact = [b for b in matches if b.period_scope == period_scope]
            return exact[0].column_name if exact else None

        for scope in ("FULL", "TO_DATE"):
            for binding in matches:
                if binding.period_scope == scope:
                    return binding.column_name

        return matches[0].column_name

    def comparison_columns(
        self,
        offsets: List[int],
        measure_kind: str = "VALUE",
    ) -> tuple:
        """
        The columns for a comparison between periods, and any caveats.

        Gate 2 Step 11b. This is the method that stops the system answering the
        same question two opposite ways.

        The current period is still running. On the sales table today that is
        five months of a twelve-month year. Compare it against a prior FULL
        year and the arithmetic is between five months and twelve:

            CY vs PY    ->  a 63% collapse
            CY vs PYTD  ->  14.5% growth

        Both are computed from the same correct data. Only one answers the
        question that was asked. So whenever the running period takes part in a
        comparison, every other period in that comparison is resolved TO_DATE.

        Where no to-date column exists for a period - the sales table has PYTD
        and nothing else - the full-year column is used and a warning is
        returned. It is a warning rather than a refusal because a caller may
        legitimately want the comparison anyway; what is not acceptable is
        making it silently.

        Returns (columns, warnings). columns is empty if any period could not
        be resolved at all, which the caller must treat as a failure rather
        than as a partial answer.
        """
        # Offset 0 is the period still in progress. If it is not part of the
        # comparison, every period involved is complete and full-year columns
        # are the right ones.
        running_period_involved = 0 in offsets

        columns: List[str] = []
        warnings: List[str] = []

        for offset in offsets:
            if offset == 0 or not running_period_involved:
                column = self.column_for_offset(offset, measure_kind)
            else:
                column = self.column_for_offset(offset, measure_kind, "TO_DATE")

                if column is None:
                    column = self.column_for_offset(offset, measure_kind)
                    if column:
                        warnings.append(
                            f"No to-date column is configured for period offset "
                            f"{offset}, so '{column}' covers a complete period "
                            f"while the current period is still running. The "
                            f"change shown will be overstated."
                        )

            if column is None:
                return [], warnings

            columns.append(column)

        return columns, warnings

    @classmethod
    def from_bindings(cls, bindings: List[SnapshotBinding]) -> "SnapshotConfig":
        """
        Wrap bindings carried on a TimeCapability so the resolver can ask the
        same questions the planner asks, without re-reading the database.
        """
        return cls(bindings=list(bindings), is_configured=bool(bindings))

    def offset_to_column(self, measure_kind: str = "VALUE") -> Dict[int, str]:
        """
        The flat offset -> column mapping that TimeCapability still speaks.

        TimeCapability.snapshot_mapping is a Dict[int, str] relied on by the
        strategy generator, the resolver, the prompt builder and eight test
        modules, so it keeps its shape. The scope-aware detail travels beside
        it in TimeCapability.snapshot_bindings.
        """
        offsets = {b.period_offset for b in self.bindings if b.measure_kind == measure_kind}
        mapping = {}

        for offset in sorted(offsets):
            column = self.column_for_offset(offset, measure_kind)
            if column:
                mapping[offset] = column

        return mapping


def _legacy_config() -> SnapshotConfig:
    """The old hardcoded behaviour, expressed as a configuration object."""
    bindings = [
        SnapshotBinding(
            period_offset=offset,
            measure_kind="VALUE",
            # Offset 0 is the running year, so it is to-date by definition; the
            # prior years the old dictionary knew were all full years.
            period_scope="TO_DATE" if offset == 0 else "FULL",
            column_name=column,
        )
        for offset, column in DEFAULT_BINDINGS.items()
    ]

    # The quantity columns were never in the old dictionary, but they WERE in
    # the hardcoded measure-column set, so the planner treated them as period
    # columns. They are given their real offsets rather than being lumped
    # together: parked on a single shared offset they would collapse to one
    # entry in offset_to_column, and resolvable_columns would then claim only
    # one of the five - quietly changing how the other four are planned.
    for offset, value_column in DEFAULT_BINDINGS.items():
        quantity_column = value_column + "Q"
        if quantity_column in DEFAULT_MEASURE_COLUMNS:
            bindings.append(SnapshotBinding(
                period_offset=offset,
                measure_kind="QUANTITY",
                period_scope="TO_DATE" if offset == 0 else "FULL",
                column_name=quantity_column,
            ))

    return SnapshotConfig(
        table_name=DEFAULT_TABLE,
        bindings=bindings,
        month_column=None,
        month_sort_column=None,
        fiscal_year_start_month=4,
        is_configured=False,
    )


class SnapshotConfigLoader:
    """Reads and caches the snapshot configuration for a connection."""

    _lock = threading.Lock()
    # Keyed on (connection_id, table_name). table_name is None for the
    # connection-wide entry that for_connection() serves, so the two never
    # collide and invalidate() can clear both in one pass.
    _cache: Dict[tuple, tuple] = {}   # (connection_id, table|None) -> (loaded_at, SnapshotConfig)

    @classmethod
    def invalidate(cls, connection_id: Optional[str] = None) -> None:
        """
        Drop cached configuration. Called when an administrator saves.

        Clears every table entry for the connection as well as the
        connection-wide one: a single admin save can change which tables are
        SNAPSHOT at all, so leaving per-table entries behind would serve stale
        bindings for a table whose strategy just changed.
        """
        with cls._lock:
            if connection_id is None:
                cls._cache.clear()
            else:
                for key in [k for k in cls._cache if k[0] == connection_id]:
                    cls._cache.pop(key, None)

    @classmethod
    def for_connection(cls, connection_id: Optional[str]) -> SnapshotConfig:
        """
        Configuration for this connection, or the legacy default.

        Never raises: a planner that cannot read its configuration must still
        produce a plan, and the caller reports the degraded state rather than
        the query failing outright.
        """
        if not connection_id:
            return _legacy_config()

        key = (connection_id, None)

        with cls._lock:
            cached = cls._cache.get(key)
            if cached and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        try:
            config = cls._load(connection_id)
        except Exception as exc:
            logger.warning(
                "Could not read snapshot configuration for %s (%s); "
                "falling back to the pre-configuration bindings.",
                connection_id, exc,
            )
            return _legacy_config()

        if not config.bindings:
            logger.warning(
                "No snapshot configuration is recorded for connection %s. "
                "Falling back to the pre-configuration bindings - run "
                "tools/seed_semantic_config.py to configure this connection.",
                connection_id,
            )
            config = _legacy_config()

        with cls._lock:
            cls._cache[key] = (time.time(), config)

        return config

    @classmethod
    def for_table(
        cls,
        connection_id: Optional[str],
        table_name: Optional[str],
    ) -> SnapshotConfig:
        """
        Gate 3 Step 7a - the snapshot configuration of ONE named table.

        WHY THIS EXISTS

        `for_connection()` answers "what is the snapshot table on this
        connection?", and its loader settles that with SELECT TOP 1 ... ORDER BY
        table_name. One SNAPSHOT table per connection therefore wins
        alphabetically and every other one is invisible. The configuration is
        per table (semantic_table_config has a row per table); the question the
        callers actually need answered is also per table - "is THIS metric's
        table a snapshot table, and if so which columns hold its periods?" -
        and the connection-wide answer cannot express that.

        HOW THIS DIFFERS FROM for_connection()

        There is no legacy fallback here, and that is the point. A table that is
        not configured SNAPSHOT must come back UNCONFIGURED, so the caller
        leaves it alone. Returning DEFAULT_BINDINGS - one customer's CY/PY/PPY
        on the wrong table - would be strictly worse than knowing nothing:
        the caller would rewrite a metric onto columns the table does not have.
        `for_connection()` keeps its fallback because its callers have no table
        to be wrong about.

        CONFIRMATION (Step 7c)

        Only is_confirmed = 1 rows are read, on both the table row and its
        period mappings. Migration 004 states the contract - "0 = system
        suggestion awaiting review... Nothing unconfirmed may be treated as
        authoritative" - and the query did not honour it, so an unreviewed
        machine suggestion could plan real SQL. An unconfirmed table now reads
        as unconfigured, which is the safe direction: the caller leaves the
        metric alone rather than binding it to columns nobody approved.

        Never raises, for the same reason for_connection() does not: a planner
        that cannot read its configuration must still produce a plan.
        """
        if not connection_id or not table_name:
            return SnapshotConfig()

        key = (connection_id, table_name)

        with cls._lock:
            cached = cls._cache.get(key)
            if cached and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        try:
            config = cls._load(connection_id, table_name)
        except Exception as exc:
            logger.warning(
                "Could not read snapshot configuration for %s on %s (%s); "
                "treating the table as unconfigured.",
                table_name, connection_id, exc,
            )
            return SnapshotConfig()

        with cls._lock:
            cls._cache[key] = (time.time(), config)

        return config

    @classmethod
    def _load(cls, connection_id: str, table_name: Optional[str] = None) -> SnapshotConfig:
        """
        Read one connection's snapshot configuration.

        With `table_name` given, the row is looked up by name and TOP 1 is not
        used - the caller has already said which table it means. Without it the
        pre-Step-7a behaviour is preserved exactly, including the alphabetical
        TOP 1, because for_connection()'s contract is "the snapshot table on
        this connection" and its callers have no table to offer.
        """
        # Imported here, not at module scope: this module is pulled in by the
        # temporal package, which the test suite imports without a database.
        from database import engine

        with engine.connect() as conn:
            if table_name:
                # Table-specific: no TOP 1, no ORDER BY. The unique constraint
                # uq_semantic_table_config (connection_id, table_name) makes
                # this at most one row, so there is nothing to disambiguate.
                # A table that is not SNAPSHOT returns no row and therefore an
                # unconfigured SnapshotConfig, which is the correct answer.
                table_row = conn.execute(text("""
                    SELECT table_name, month_column, month_sort_column,
                           fiscal_year_start_month
                    FROM semantic_table_config
                    WHERE connection_id = :connection_id
                      AND table_name = :table_name
                      AND temporal_strategy = 'SNAPSHOT'
                      AND is_confirmed = 1
                """), {
                    "connection_id": connection_id,
                    "table_name": table_name,
                }).fetchone()
            else:
                table_row = conn.execute(text("""
                    SELECT TOP 1 table_name, month_column, month_sort_column,
                           fiscal_year_start_month
                    FROM semantic_table_config
                    WHERE connection_id = :connection_id
                      AND temporal_strategy = 'SNAPSHOT'
                      AND is_confirmed = 1
                    ORDER BY table_name
                """), {"connection_id": connection_id}).fetchone()

            if not table_row:
                return SnapshotConfig()

            mapping_rows = conn.execute(text("""
                SELECT period_offset, measure_kind, period_scope, column_name
                FROM semantic_snapshot_mapping
                WHERE connection_id = :connection_id
                  AND table_name = :table_name
                  AND is_confirmed = 1
                ORDER BY period_offset, measure_kind, period_scope
            """), {
                "connection_id": connection_id,
                "table_name": table_row[0],
            }).fetchall()

        return SnapshotConfig(
            table_name=table_row[0],
            bindings=[
                SnapshotBinding(
                    period_offset=row[0],
                    measure_kind=row[1],
                    period_scope=row[2],
                    column_name=row[3],
                )
                for row in mapping_rows
            ],
            month_column=table_row[1],
            month_sort_column=table_row[2],
            # Gate 3 Step 7b - the configured value is authoritative. This read
            # `table_row[3] or 4`, which silently replaced a configured 1 with
            # April: `or` treats 1 as truthy, so January survived, but a NULL
            # became April rather than the calendar default the column's own
            # DEFAULT constraint specifies. Only a genuinely absent value now
            # falls back, and it falls back to the dataclass default.
            fiscal_year_start_month=(
                table_row[3] if table_row[3] is not None else 4
            ),
            is_configured=bool(mapping_rows),
        )
