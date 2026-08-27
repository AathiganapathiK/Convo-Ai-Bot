"""
Gate 2 - request/response schemas for the semantic configuration API.

These describe the shape of admin-configurable semantic meaning: business
domains, per-table time behaviour, snapshot period mappings, dimension roles
and column exclusions.

Every model here maps onto tables created by migration 004_semantic_config.sql.
No schema in this file implies any table that does not already exist.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Allowed values - mirrored from the CHECK constraints in migration 004.
#
# These are duplicated as plain tuples rather than imported from the migration
# so that a bad value is rejected by the API with a 422 and a readable message,
# instead of reaching SQL Server and coming back as a constraint violation.
# ---------------------------------------------------------------------------

TEMPORAL_STRATEGIES = ("SNAPSHOT", "DATE_COLUMN", "NONE")

MEASURE_KINDS = ("VALUE", "QUANTITY")

PERIOD_SCOPES = ("FULL", "TO_DATE")

# dimension_role is NVARCHAR(30) with no CHECK constraint in migration 004, so
# the database accepts anything. The API constrains it anyway - an unconstrained
# free-text role is how "TIME_LABEL" and "Time Label" end up as two roles.
DIMENSION_ROLES = (
    "GROUPING",     # may be grouped on in a GROUP BY
    "TIME_LABEL",   # a period label such as InvMonth
    "IDENTIFIER",   # a key or document number, never a grouping
    "INTERNAL",     # exists but is not offered to business users
)


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------

class DomainRequest(BaseModel):
    domain_name: str = Field(min_length=1, max_length=128)
    business_name: str = Field(min_length=1, max_length=128)
    synonyms: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True


class DomainActiveRequest(BaseModel):
    is_active: bool


# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------

class TableConfigRequest(BaseModel):
    """
    Per-table time behaviour and domain binding.

    Every field is optional because a table may be configured progressively -
    bound to a domain today, given its temporal strategy tomorrow. domain_id
    stays nullable by design: an unassigned table must fail loudly at query
    time rather than silently defaulting to some domain.
    """

    domain_id: Optional[str] = None
    temporal_strategy: Optional[str] = None
    date_column: Optional[str] = None
    month_column: Optional[str] = None
    month_sort_column: Optional[str] = None
    fiscal_year_start_month: int = 1
    is_confirmed: bool = False


# ---------------------------------------------------------------------------
# Snapshot mappings
# ---------------------------------------------------------------------------

class SnapshotMappingItem(BaseModel):
    """
    One period column on a snapshot table.

    period_scope is the field that matters most. On the live sales table CY
    holds the current fiscal year TO DATE while PY holds the previous fiscal
    year IN FULL, so comparing them directly reports a collapse that did not
    happen. PY and PYTD are two rows here, differing only in period_scope, and
    the UI must never present them as a duplicate to be tidied away.
    """

    period_offset: int = Field(ge=0)
    measure_kind: str = "VALUE"
    period_scope: str = "FULL"
    column_name: str = Field(min_length=1, max_length=128)
    is_confirmed: bool = False


class SnapshotMappingSetRequest(BaseModel):
    """
    The complete set of snapshot mappings for one table.

    Deliberately replace-the-set rather than per-row CRUD: the FULL/TO_DATE
    pair is only meaningful together, so the set is validated as a whole.
    """

    mappings: List[SnapshotMappingItem]


# ---------------------------------------------------------------------------
# Dimension and metric configuration
# ---------------------------------------------------------------------------

class DimensionConfigRequest(BaseModel):
    dimension_role: Optional[str] = None
    is_excluded: Optional[bool] = None
    is_confirmed: Optional[bool] = None


class MetricConfigRequest(BaseModel):
    aggregation_type: Optional[str] = None
    is_excluded: Optional[bool] = None
    is_confirmed: Optional[bool] = None


# ---------------------------------------------------------------------------
# Suggestions
#
# These describe what Gate 2 Step 8 will produce. Step 8 is not implemented at
# the time of writing, so the API serves this shape from a development fixture.
# The shape is the contract; the source behind it is expected to change once
# the suggestion service exists.
# ---------------------------------------------------------------------------

class SuggestionConfirmRequest(BaseModel):
    """
    Confirm a suggestion, optionally with reviewer edits.

    A reviewer who corrects a proposal before accepting it is the entire point
    of the review step, so edited_proposal carries the corrected values and
    overrides the machine's proposal field by field.
    """

    edited_proposal: Optional[dict] = None


class SuggestionRejectRequest(BaseModel):
    reason: Optional[str] = None
