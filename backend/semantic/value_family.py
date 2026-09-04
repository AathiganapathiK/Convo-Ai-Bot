"""
Curated value families, read from semantic_value_family.

WHAT A FAMILY IS

A grouping of stored dimension values under the name a user actually says.
The live case is Brand: PBI_ENES_ORDER_PENDING_SUMMARY.Brand holds brand x
product-line pairs (RAMRAJ DHOTI, RAMRAJ PANT, VIVEAGHAM DHOTI, ...), so the
brand itself - "Ramraj" - is not a stored value. A family records that RAMRAJ
means those twelve rows.

WHAT THIS DELIBERATELY DOES NOT DO

No inference. Membership is read from the table and nothing else - no prefix
rule, no fuzzy expansion, no first-token split. Migration 008's header records
why: VIVEAGA and VIVEAGHAM may or may not be one brand, RAMYYAM SAREE shares a
stem with RAMRAJ, and BAHAMA / GENISTAA / KOKHILA / UNIBRO are bare brands with
no suffix at all. A string rule gets at least one of those wrong silently.

Nothing here is specific to brands or to any particular family. The resolver
asks "does this connection curate families on this dimension?" and the answer
comes entirely from configuration.

CONFIRMATION

Only is_confirmed = 1 rows are read, consistent with semantic_table_config and
semantic_snapshot_mapping. An unreviewed family is not authoritative, and the
resolver then behaves as though no family were configured - which surfaces the
ambiguity rather than answering from a suggestion nobody approved.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Matches SnapshotConfigLoader: the resolver runs this on every question, so it
# cannot be a database round trip each time. An administrator's save calls
# invalidate() directly, so the window only matters for a change made outside
# the application.
CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class ValueFamily:
    """One curated family: a name, where it lives, and what it contains."""

    family_name: str
    dimension_id: str
    business_name: str
    table_name: str
    column_name: str
    members: Tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        """
        A family with fewer than two members is not a family.

        One member is just a rename, and the stored value already matches on
        its own spelling; zero members cannot expand to anything. Offering
        either as a family value would put a name in front of the user that
        resolves to something narrower than it claims.
        """
        return len(self.members) >= 2


@dataclass
class ValueFamilyConfig:
    """Every family configured for one connection."""

    families: List[ValueFamily] = field(default_factory=list)

    @property
    def is_configured(self) -> bool:
        return bool(self.families)

    def usable(self) -> List[ValueFamily]:
        return [f for f in self.families if f.is_usable]

    def members_for(
        self,
        table_name: Optional[str],
        column_name: Optional[str],
        family_name: Optional[str],
    ) -> Tuple[str, ...]:
        """
        The members of one family, or () when there is no such family.

        Looked up on physical identity plus name, so a family never leaks
        across dimensions that happen to share a family name.
        """
        if not (table_name and column_name and family_name):
            return ()

        for family in self.families:
            if (
                family.table_name.lower() == table_name.lower()
                and family.column_name.lower() == column_name.lower()
                and family.family_name.lower() == family_name.lower()
            ):
                return family.members

        return ()


class ValueFamilyLoader:
    """Reads and caches the curated families for a connection."""

    _lock = threading.Lock()
    _cache: Dict[str, tuple] = {}   # connection_id -> (loaded_at, ValueFamilyConfig)

    @classmethod
    def invalidate(cls, connection_id: Optional[str] = None) -> None:
        """Drop cached families. Called when an administrator saves."""
        with cls._lock:
            if connection_id is None:
                cls._cache.clear()
            else:
                cls._cache.pop(connection_id, None)

    @classmethod
    def for_connection(cls, connection_id: Optional[str]) -> ValueFamilyConfig:
        """
        The families configured for this connection.

        Never raises. A resolver that cannot read its configuration must still
        answer the question; it simply answers it without families, which is
        the pre-008 behaviour.
        """
        if not connection_id:
            return ValueFamilyConfig()

        with cls._lock:
            cached = cls._cache.get(connection_id)
            if cached and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
                return cached[1]

        try:
            config = cls._load(connection_id)
        except Exception as exc:
            logger.warning(
                "Could not read value families for %s (%s); continuing "
                "without them.",
                connection_id, exc,
            )
            return ValueFamilyConfig()

        with cls._lock:
            cls._cache[connection_id] = (time.time(), config)

        return config

    @classmethod
    def _load(cls, connection_id: str) -> ValueFamilyConfig:
        # Imported here, not at module scope, so the unit tests can import this
        # module without a database - the same reason snapshot_config does it.
        from database import engine
        from semantic import runtime_config_filter

        rows = []
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT vf.family_name, vf.member_value,
                       sd.dimension_id, sd.business_name,
                       sd.table_name, sd.column_name
                FROM semantic_value_family vf
                INNER JOIN semantic_dimensions sd
                    ON sd.dimension_id = vf.dimension_id
                WHERE vf.connection_id = :connection_id
                  AND vf.is_confirmed = 1
                  AND sd.is_active = 1
                  {runtime_config_filter.dimension_filter("sd")}
                ORDER BY sd.table_name, sd.column_name,
                         vf.family_name, vf.member_value
            """), {"connection_id": connection_id}).fetchall()

        # Grouped on physical identity plus family name, so two dimensions may
        # each carry a family of the same name without merging.
        grouped: Dict[tuple, dict] = {}
        for family_name, member_value, dimension_id, business_name, table_name, column_name in rows:
            if not family_name or not member_value:
                continue
            key = (str(dimension_id), family_name)
            entry = grouped.setdefault(key, {
                "family_name": family_name,
                "dimension_id": str(dimension_id),
                "business_name": business_name,
                "table_name": table_name,
                "column_name": column_name,
                "members": [],
            })
            entry["members"].append(member_value)

        families = [
            ValueFamily(
                family_name=entry["family_name"],
                dimension_id=entry["dimension_id"],
                business_name=entry["business_name"],
                table_name=entry["table_name"],
                column_name=entry["column_name"],
                members=tuple(entry["members"]),
            )
            for entry in grouped.values()
        ]

        unusable = [f.family_name for f in families if not f.is_usable]
        if unusable:
            logger.warning(
                "Value families with fewer than two members are ignored: %s",
                ", ".join(sorted(set(unusable))),
            )

        return ValueFamilyConfig(families=families)
