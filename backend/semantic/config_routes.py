"""
Gate 2 Step 9 - the semantic configuration API.

Endpoints for the configuration that teaches the system what columns mean:
business domains, per-table time behaviour, snapshot period mappings,
dimension roles, column exclusions, and the review queue for machine
suggestions.

Deliberately a separate router file rather than more endpoints in app.py.
app.py is approaching two thousand lines and every endpoint anyone adds lands
in it, which makes it the most likely place in the project for a merge
conflict. This follows the pattern already set by auth/auth_router.py and
configuration/config_routes.py.

Authorisation reuses the project's existing scheme. Reads require an
authenticated user; writes require "semantic:write", which
security/rbac_service.py already maps to the page:semantic:m permission seeded
by migration 004_access_control_extension.sql. No new permission is introduced
and no new authentication path exists here.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth.dependencies import get_current_user
from security.rbac_service import require_permission

from semantic.config_schema import (
    DIMENSION_ROLES,
    MEASURE_KINDS,
    PERIOD_SCOPES,
    TEMPORAL_STRATEGIES,
    DimensionConfigRequest,
    DomainActiveRequest,
    DomainRequest,
    MetricConfigRequest,
    SnapshotMappingSetRequest,
    SuggestionConfirmRequest,
    SuggestionGenerateRequest,
    SuggestionRejectRequest,
    TableConfigRequest,
)
from semantic.config_service import (
    ColumnConfigService,
    ColumnStateService,
    DomainService,
    SnapshotMappingService,
    SuggestionService,
    TableConfigService,
    get_active_connection_id,
)


router = APIRouter(
    prefix="/semantic/config",
    tags=["Semantic Configuration"]
)


# ---------------------------------------------------------------------------
# Validation helpers
#
# These mirror the CHECK constraints in migration 004. Checking here turns a
# bad value into a readable 400 instead of a driver-level constraint violation.
# ---------------------------------------------------------------------------

def _reject_unknown(value: Optional[str], allowed: tuple, field: str):
    if value is None:
        return

    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{field} must be one of {', '.join(allowed)}. "
                f"Received '{value}'."
            )
        )


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

@router.get("/options")
def get_config_options(user=Depends(get_current_user)):
    """
    The allowed values for every constrained configuration field.

    Served rather than hardcoded in the frontend so that the screens and the
    database constraints cannot drift apart.
    """

    return {
        "temporal_strategies": list(TEMPORAL_STRATEGIES),
        "measure_kinds": list(MEASURE_KINDS),
        "period_scopes": list(PERIOD_SCOPES),
        "dimension_roles": list(DIMENSION_ROLES)
    }


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

@router.post("/suggestions/generate", status_code=status.HTTP_202_ACCEPTED)
def generate_suggestions(
    request: SuggestionGenerateRequest,
    user=Depends(require_permission("semantic:write"))
):
    """
    Profile the active connection and propose configuration for it.

    Accepted, not completed: a run costs a profiling scan and several paced
    model calls per table - minutes, not milliseconds - so it runs in the
    background and the caller polls /suggestions/generation. Returning 202
    rather than holding the request open keeps it clear of every proxy and
    browser timeout between here and the screen.

    Writes require semantic:write for the same reason confirming does: a run
    replaces the review queue, and a queue is what an administrator works from.
    Nothing it produces is applied to the configuration until somebody confirms
    it, and a decision already made on an unchanged proposal is preserved.
    """

    return SuggestionService.start_generation(
        table_names=request.table_names,
        use_model=request.use_model,
        user=user
    )


@router.get("/suggestions/generation")
def generation_status(user=Depends(get_current_user)):
    """
    Where the current or last run got to.

    A read, so an ordinary authenticated user may poll it - the screen shows
    the state to whoever has the page open, not only to whoever started it.
    """

    return SuggestionService.generation_status()


@router.get("/suggestions")
def list_suggestions(
    table_name: Optional[str] = Query(default=None),
    include_rejected: bool = Query(default=False),
    user=Depends(get_current_user)
):
    """
    The review queue.

    The response carries source_status, which states whether these came from a
    real profiling run or from development fixture data. The screens show that
    verbatim: an unconfirmed machine proposal must never be presented as fact.
    """

    return SuggestionService.list_suggestions(
        table_name=table_name,
        include_rejected=include_rejected
    )


@router.get("/suggestions/{suggestion_id}")
def get_suggestion(
    suggestion_id: str,
    user=Depends(get_current_user)
):
    return SuggestionService.get_suggestion(suggestion_id)


@router.post("/suggestions/{suggestion_id}/confirm")
def confirm_suggestion(
    suggestion_id: str,
    request: SuggestionConfirmRequest,
    user=Depends(require_permission("semantic:write"))
):
    """
    Accept a suggestion, optionally with reviewer corrections, and write it
    into the configuration tables.
    """

    connection_id = get_active_connection_id()

    edited = request.edited_proposal or {}

    _reject_unknown(
        edited.get("temporal_strategy"),
        TEMPORAL_STRATEGIES,
        "temporal_strategy"
    )

    _reject_unknown(
        edited.get("dimension_role"),
        DIMENSION_ROLES,
        "dimension_role"
    )

    return SuggestionService.confirm_suggestion(
        connection_id=connection_id,
        suggestion_id=suggestion_id,
        edited_proposal=request.edited_proposal,
        user=user
    )


@router.post("/suggestions/{suggestion_id}/reject")
def reject_suggestion(
    suggestion_id: str,
    request: SuggestionRejectRequest,
    user=Depends(require_permission("semantic:write"))
):
    """
    Reject a suggestion.

    Durable since migration 007 added review_status to the suggestion store, so
    a declined suggestion stays declined across a restart and a reviewer can
    work through the list over more than one sitting.
    """

    return SuggestionService.reject_suggestion(
        suggestion_id=suggestion_id,
        reason=request.reason,
        user=user
    )


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------

@router.get("/domains")
def list_domains(user=Depends(get_current_user)):
    connection_id = get_active_connection_id()

    return DomainService.list_domains(connection_id)


@router.post("/domains")
def create_domain(
    request: DomainRequest,
    user=Depends(require_permission("semantic:write"))
):
    connection_id = get_active_connection_id()

    return DomainService.create_domain(
        connection_id=connection_id,
        data=request.model_dump(),
        user=user
    )


@router.put("/domains/{domain_id}")
def update_domain(
    domain_id: str,
    request: DomainRequest,
    user=Depends(require_permission("semantic:write"))
):
    return DomainService.update_domain(
        domain_id=domain_id,
        data=request.model_dump(),
        user=user
    )


@router.patch("/domains/{domain_id}/active")
def set_domain_active(
    domain_id: str,
    request: DomainActiveRequest,
    user=Depends(require_permission("semantic:write"))
):
    return DomainService.set_domain_active(
        domain_id=domain_id,
        is_active=request.is_active,
        user=user
    )


# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------

@router.get("/tables")
def list_table_configs(user=Depends(get_current_user)):
    connection_id = get_active_connection_id()

    return TableConfigService.list_table_configs(connection_id)


@router.get("/tables/{table_name}")
def get_table_config(
    table_name: str,
    user=Depends(get_current_user)
):
    connection_id = get_active_connection_id()

    return TableConfigService.get_table_config(
        connection_id=connection_id,
        table_name=table_name
    )


@router.put("/tables/{table_name}")
def update_table_config(
    table_name: str,
    request: TableConfigRequest,
    user=Depends(require_permission("semantic:write"))
):
    connection_id = get_active_connection_id()

    _reject_unknown(
        request.temporal_strategy,
        TEMPORAL_STRATEGIES,
        "temporal_strategy"
    )

    return TableConfigService.upsert_table_config(
        connection_id=connection_id,
        table_name=table_name,
        data=request.model_dump(),
        user=user
    )


# ---------------------------------------------------------------------------
# Snapshot mappings
# ---------------------------------------------------------------------------

@router.get("/tables/{table_name}/snapshot-mappings")
def list_snapshot_mappings(
    table_name: str,
    user=Depends(get_current_user)
):
    connection_id = get_active_connection_id()

    return SnapshotMappingService.list_mappings(
        connection_id=connection_id,
        table_name=table_name
    )


@router.put("/tables/{table_name}/snapshot-mappings")
def replace_snapshot_mappings(
    table_name: str,
    request: SnapshotMappingSetRequest,
    user=Depends(require_permission("semantic:write"))
):
    """
    Replace the whole set of period mappings for one table.

    The set is written as a unit because the FULL and TO_DATE rows for a period
    are only meaningful together. The response may carry warnings describing a
    comparison shape that would mislead - a partial current period measured
    against a complete previous one.
    """

    connection_id = get_active_connection_id()

    for m in request.mappings:
        _reject_unknown(m.measure_kind, MEASURE_KINDS, "measure_kind")
        _reject_unknown(m.period_scope, PERIOD_SCOPES, "period_scope")

    return SnapshotMappingService.replace_mappings(
        connection_id=connection_id,
        table_name=table_name,
        mappings=[m.model_dump() for m in request.mappings],
        user=user
    )


@router.delete("/snapshot-mappings/{mapping_id}")
def delete_snapshot_mapping(
    mapping_id: str,
    user=Depends(require_permission("semantic:write"))
):
    return SnapshotMappingService.delete_mapping(mapping_id)


# ---------------------------------------------------------------------------
# Dimension and metric configuration
# ---------------------------------------------------------------------------

@router.get("/columns")
def list_column_state(user=Depends(get_current_user)):
    """
    Role, exclusion and confirmation state for every configured column.

    Served here rather than added to /semantic/metrics and /semantic/dimensions
    so that semantic_service.py - a file shared between both tracks - keeps
    returning exactly what it returned before. The screens merge this alongside
    the existing lists by id.
    """

    connection_id = get_active_connection_id()

    return ColumnStateService.list_column_state(connection_id)


@router.patch("/dimensions/{dimension_id}")
def update_dimension_config(
    dimension_id: str,
    request: DimensionConfigRequest,
    user=Depends(require_permission("semantic:write"))
):
    _reject_unknown(
        request.dimension_role,
        DIMENSION_ROLES,
        "dimension_role"
    )

    return ColumnConfigService.update_dimension_config(
        dimension_id=dimension_id,
        data=request.model_dump(),
        user=user
    )


@router.patch("/metrics/{metric_id}")
def update_metric_config(
    metric_id: str,
    request: MetricConfigRequest,
    user=Depends(require_permission("semantic:write"))
):
    return ColumnConfigService.update_metric_config(
        metric_id=metric_id,
        data=request.model_dump(),
        user=user
    )
