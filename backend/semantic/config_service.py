"""
Gate 2 - data access for the semantic configuration API.

Reads and writes the tables created by migration 004_semantic_config.sql:
semantic_domains, semantic_table_config, semantic_snapshot_mapping, and the
role/exclusion/confirmation columns added to semantic_dimensions and
semantic_metrics.

This module creates no tables and alters no schema. Migrations are owned
elsewhere; every statement here is a SELECT, INSERT, UPDATE or DELETE against
objects that already exist.

Suggestions are a special case and are documented at the suggestion section
below: Gate 2 Step 8 (the suggestion service) is not implemented yet, so
suggestions are served from a development fixture behind a single seam.
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import text

from database import engine
from services.connection_service import ConnectionService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Active connection
#
# app.py defines an identical helper, but importing it here would be circular:
# app.py imports this router, so this module must not import app.py. The call
# underneath is the same one app.py makes, so both resolve the same connection.
# ---------------------------------------------------------------------------

def get_active_connection_id() -> str:
    conn = ConnectionService.get_active_connection_global()

    if not conn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active database connection configured."
        )

    return conn["connection_id"]


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------

class DomainService:

    @staticmethod
    def list_domains(connection_id: str):
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        domain_id,
                        connection_id,
                        domain_name,
                        business_name,
                        synonyms,
                        description,
                        is_active,
                        created_at,
                        updated_at
                    FROM semantic_domains
                    WHERE connection_id = :connection_id
                    ORDER BY business_name
                """),
                {"connection_id": connection_id}
            ).fetchall()

        return [_row_to_dict(r) for r in rows]

    @staticmethod
    def create_domain(connection_id: str, data: dict, user: dict):
        with engine.begin() as conn:

            duplicate = conn.execute(
                text("""
                    SELECT 1
                    FROM semantic_domains
                    WHERE connection_id = :connection_id
                      AND LOWER(domain_name) = LOWER(:domain_name)
                """),
                {
                    "connection_id": connection_id,
                    "domain_name": data["domain_name"]
                }
            ).fetchone()

            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Domain '{data['domain_name']}' already exists."
                )

            domain_id = str(uuid.uuid4())

            conn.execute(
                text("""
                    INSERT INTO semantic_domains
                    (
                        domain_id,
                        connection_id,
                        domain_name,
                        business_name,
                        synonyms,
                        description,
                        is_active,
                        created_by,
                        updated_by
                    )
                    VALUES
                    (
                        :domain_id,
                        :connection_id,
                        :domain_name,
                        :business_name,
                        :synonyms,
                        :description,
                        :is_active,
                        :created_by,
                        :updated_by
                    )
                """),
                {
                    "domain_id": domain_id,
                    "connection_id": connection_id,
                    "domain_name": data["domain_name"],
                    "business_name": data["business_name"],
                    "synonyms": data.get("synonyms"),
                    "description": data.get("description"),
                    "is_active": 1 if data.get("is_active", True) else 0,
                    "created_by": user["employee_id"],
                    "updated_by": user["employee_id"]
                }
            )

        return {
            "message": "Domain created successfully.",
            "domain_id": domain_id
        }

    @staticmethod
    def update_domain(domain_id: str, data: dict, user: dict):
        with engine.begin() as conn:

            existing = conn.execute(
                text("SELECT 1 FROM semantic_domains WHERE domain_id = :domain_id"),
                {"domain_id": domain_id}
            ).fetchone()

            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Domain not found."
                )

            conn.execute(
                text("""
                    UPDATE semantic_domains
                    SET domain_name   = :domain_name,
                        business_name = :business_name,
                        synonyms      = :synonyms,
                        description   = :description,
                        is_active     = :is_active,
                        updated_at    = GETDATE(),
                        updated_by    = :updated_by
                    WHERE domain_id = :domain_id
                """),
                {
                    "domain_id": domain_id,
                    "domain_name": data["domain_name"],
                    "business_name": data["business_name"],
                    "synonyms": data.get("synonyms"),
                    "description": data.get("description"),
                    "is_active": 1 if data.get("is_active", True) else 0,
                    "updated_by": user["employee_id"]
                }
            )

        return {"message": "Domain updated successfully."}

    @staticmethod
    def set_domain_active(domain_id: str, is_active: bool, user: dict):
        with engine.begin() as conn:

            result = conn.execute(
                text("""
                    UPDATE semantic_domains
                    SET is_active  = :is_active,
                        updated_at = GETDATE(),
                        updated_by = :updated_by
                    WHERE domain_id = :domain_id
                """),
                {
                    "domain_id": domain_id,
                    "is_active": 1 if is_active else 0,
                    "updated_by": user["employee_id"]
                }
            )

            if result.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Domain not found."
                )

        return {"message": "Domain updated successfully."}


# ---------------------------------------------------------------------------
# Table configuration
#
# Addressed by table_name rather than config_id: the unique key is
# (connection_id, table_name), and the caller always knows the table name.
# ---------------------------------------------------------------------------

class TableConfigService:

    @staticmethod
    def list_table_configs(connection_id: str):
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        tc.config_id,
                        tc.table_name,
                        tc.domain_id,
                        d.domain_name,
                        d.business_name AS domain_business_name,
                        tc.temporal_strategy,
                        tc.date_column,
                        tc.month_column,
                        tc.month_sort_column,
                        tc.fiscal_year_start_month,
                        tc.is_confirmed,
                        tc.updated_at
                    FROM semantic_table_config tc
                    LEFT JOIN semantic_domains d
                           ON d.domain_id = tc.domain_id
                    WHERE tc.connection_id = :connection_id
                    ORDER BY tc.table_name
                """),
                {"connection_id": connection_id}
            ).fetchall()

        return [_row_to_dict(r) for r in rows]

    @staticmethod
    def get_table_config(connection_id: str, table_name: str):
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT
                        tc.config_id,
                        tc.table_name,
                        tc.domain_id,
                        d.domain_name,
                        tc.temporal_strategy,
                        tc.date_column,
                        tc.month_column,
                        tc.month_sort_column,
                        tc.fiscal_year_start_month,
                        tc.is_confirmed,
                        tc.updated_at
                    FROM semantic_table_config tc
                    LEFT JOIN semantic_domains d
                           ON d.domain_id = tc.domain_id
                    WHERE tc.connection_id = :connection_id
                      AND tc.table_name = :table_name
                """),
                {
                    "connection_id": connection_id,
                    "table_name": table_name
                }
            ).fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No configuration recorded for table '{table_name}'."
            )

        return _row_to_dict(row)

    @staticmethod
    def upsert_table_config(
        connection_id: str,
        table_name: str,
        data: dict,
        user: dict
    ):
        """
        Create or update one table's configuration.

        Upsert rather than separate create/update because the caller does not
        know, and should not have to know, whether a row exists yet - the
        configuration tables start empty.
        """

        TableConfigService._validate(data)

        params = {
            "connection_id": connection_id,
            "table_name": table_name,
            "domain_id": data.get("domain_id"),
            "temporal_strategy": data.get("temporal_strategy"),
            "date_column": data.get("date_column"),
            "month_column": data.get("month_column"),
            "month_sort_column": data.get("month_sort_column"),
            "fiscal_year_start_month": data.get("fiscal_year_start_month", 1),
            "is_confirmed": 1 if data.get("is_confirmed") else 0,
            "user_id": user["employee_id"]
        }

        with engine.begin() as conn:

            existing = conn.execute(
                text("""
                    SELECT config_id
                    FROM semantic_table_config
                    WHERE connection_id = :connection_id
                      AND table_name = :table_name
                """),
                {
                    "connection_id": connection_id,
                    "table_name": table_name
                }
            ).fetchone()

            if existing:
                conn.execute(
                    text("""
                        UPDATE semantic_table_config
                        SET domain_id               = :domain_id,
                            temporal_strategy       = :temporal_strategy,
                            date_column             = :date_column,
                            month_column            = :month_column,
                            month_sort_column       = :month_sort_column,
                            fiscal_year_start_month = :fiscal_year_start_month,
                            is_confirmed            = :is_confirmed,
                            updated_at              = GETDATE(),
                            updated_by              = :user_id
                        WHERE connection_id = :connection_id
                          AND table_name = :table_name
                    """),
                    params
                )

                config_id = existing[0]

            else:
                config_id = str(uuid.uuid4())
                params["config_id"] = config_id

                conn.execute(
                    text("""
                        INSERT INTO semantic_table_config
                        (
                            config_id,
                            connection_id,
                            table_name,
                            domain_id,
                            temporal_strategy,
                            date_column,
                            month_column,
                            month_sort_column,
                            fiscal_year_start_month,
                            is_confirmed,
                            created_by,
                            updated_by
                        )
                        VALUES
                        (
                            :config_id,
                            :connection_id,
                            :table_name,
                            :domain_id,
                            :temporal_strategy,
                            :date_column,
                            :month_column,
                            :month_sort_column,
                            :fiscal_year_start_month,
                            :is_confirmed,
                            :user_id,
                            :user_id
                        )
                    """),
                    params
                )

        _invalidate_snapshot_cache(connection_id)

        return {
            "message": "Table configuration saved.",
            "config_id": str(config_id)
        }

    @staticmethod
    def _validate(data: dict):
        """
        Reject configurations that the temporal resolver could not act on.

        These checks exist because a half-configured table is worse than an
        unconfigured one: an unconfigured table fails loudly, while a table
        declaring DATE_COLUMN with no date column fails at query time.
        """

        strategy = data.get("temporal_strategy")

        if strategy == "DATE_COLUMN" and not data.get("date_column"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "temporal_strategy DATE_COLUMN requires a date_column. "
                    "Without one the resolver has no column to filter on."
                )
            )

        month = data.get("month_column")
        sort = data.get("month_sort_column")

        if sort and not month:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "month_sort_column was given without a month_column. "
                    "The sort column orders the month column; it cannot stand alone."
                )
            )


# ---------------------------------------------------------------------------
# Snapshot mappings
#
# Replace-the-set rather than per-row CRUD. The FULL and TO_DATE rows for the
# same period are only meaningful together: deleting the TO_DATE row for last
# year leaves a configuration that compares a partial current year against a
# full previous year, which is the documented comparison trap.
# ---------------------------------------------------------------------------

def _invalidate_snapshot_cache(connection_id: str) -> None:
    """
    Drop the planner's cached copy of this connection's snapshot configuration.

    The plan builder reads configuration on every question, so it caches. An
    administrator who saves a mapping and then asks a question expects the new
    mapping to be used, not one up to CACHE_TTL_SECONDS old.
    """
    try:
        from semantic.temporal.snapshot_config import SnapshotConfigLoader
        SnapshotConfigLoader.invalidate(connection_id)
    except Exception as exc:
        # A stale cache is a small problem; failing the save is a large one.
        logger.warning("Could not invalidate the snapshot config cache: %s", exc)


class SnapshotMappingService:

    @staticmethod
    def list_mappings(connection_id: str, table_name: str):
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        mapping_id,
                        table_name,
                        period_offset,
                        measure_kind,
                        period_scope,
                        column_name,
                        is_confirmed,
                        updated_at
                    FROM semantic_snapshot_mapping
                    WHERE connection_id = :connection_id
                      AND table_name = :table_name
                    ORDER BY period_offset, measure_kind, period_scope
                """),
                {
                    "connection_id": connection_id,
                    "table_name": table_name
                }
            ).fetchall()

        return [_row_to_dict(r) for r in rows]

    @staticmethod
    def replace_mappings(
        connection_id: str,
        table_name: str,
        mappings: list,
        user: dict
    ):
        warnings = SnapshotMappingService.check_set(mappings)

        seen = set()

        for m in mappings:
            key = (
                m["period_offset"],
                m["measure_kind"],
                m["period_scope"]
            )

            if key in seen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Duplicate mapping for period_offset={key[0]}, "
                        f"measure_kind={key[1]}, period_scope={key[2]}. "
                        "The database enforces one column per combination."
                    )
                )

            seen.add(key)

        with engine.begin() as conn:

            conn.execute(
                text("""
                    DELETE FROM semantic_snapshot_mapping
                    WHERE connection_id = :connection_id
                      AND table_name = :table_name
                """),
                {
                    "connection_id": connection_id,
                    "table_name": table_name
                }
            )

            for m in mappings:
                conn.execute(
                    text("""
                        INSERT INTO semantic_snapshot_mapping
                        (
                            mapping_id,
                            connection_id,
                            table_name,
                            period_offset,
                            measure_kind,
                            period_scope,
                            column_name,
                            is_confirmed,
                            created_by,
                            updated_by
                        )
                        VALUES
                        (
                            :mapping_id,
                            :connection_id,
                            :table_name,
                            :period_offset,
                            :measure_kind,
                            :period_scope,
                            :column_name,
                            :is_confirmed,
                            :user_id,
                            :user_id
                        )
                    """),
                    {
                        "mapping_id": str(uuid.uuid4()),
                        "connection_id": connection_id,
                        "table_name": table_name,
                        "period_offset": m["period_offset"],
                        "measure_kind": m["measure_kind"],
                        "period_scope": m["period_scope"],
                        "column_name": m["column_name"],
                        "is_confirmed": 1 if m.get("is_confirmed") else 0,
                        "user_id": user["employee_id"]
                    }
                )

        _invalidate_snapshot_cache(connection_id)

        return {
            "message": "Snapshot mappings saved.",
            "count": len(mappings),
            "warnings": warnings
        }

    @staticmethod
    def check_set(mappings: list) -> list:
        """
        Warn - never block - on comparison shapes known to mislead.

        A warning rather than a rejection because the reviewer may genuinely be
        configuring a table where no to-date column exists. The point is that
        they should not be able to do it without being told.
        """

        warnings = []

        current_to_date = any(
            m["period_offset"] == 0
            and m["period_scope"] == "TO_DATE"
            for m in mappings
        )

        if not current_to_date:
            return warnings

        for m in mappings:
            if m["period_offset"] == 0:
                continue

            if m["period_scope"] != "FULL":
                continue

            has_to_date = any(
                o["period_offset"] == m["period_offset"]
                and o["measure_kind"] == m["measure_kind"]
                and o["period_scope"] == "TO_DATE"
                for o in mappings
            )

            if not has_to_date:
                warnings.append(
                    f"Period offset {m['period_offset']} ({m['measure_kind']}) "
                    f"has a FULL column '{m['column_name']}' but no TO_DATE "
                    "column. The current period is to-date, so a comparison "
                    "against this column compares a partial period against a "
                    "complete one and will overstate the change."
                )

        return warnings

    @staticmethod
    def delete_mapping(mapping_id: str):
        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    DELETE FROM semantic_snapshot_mapping
                    WHERE mapping_id = :mapping_id
                """),
                {"mapping_id": mapping_id}
            )

            if result.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Snapshot mapping not found."
                )

        return {"message": "Snapshot mapping deleted."}


# ---------------------------------------------------------------------------
# Dimension and metric configuration
#
# Partial updates against the columns migration 004 added. Only the fields the
# caller supplies are written, so a screen that edits the role does not have to
# resend the exclusion flag and risk clobbering it.
# ---------------------------------------------------------------------------

class ColumnConfigService:

    @staticmethod
    def update_dimension_config(dimension_id: str, data: dict, user: dict):
        return ColumnConfigService._patch(
            table="semantic_dimensions",
            id_column="dimension_id",
            record_id=dimension_id,
            allowed=(
                "business_name", "description", "synonyms",
                "dimension_role", "is_excluded", "is_confirmed",
            ),
            bool_fields=("is_excluded", "is_confirmed"),
            data=data,
            user=user,
            not_found="Dimension not found."
        )

    @staticmethod
    def update_metric_config(metric_id: str, data: dict, user: dict):
        return ColumnConfigService._patch(
            table="semantic_metrics",
            id_column="metric_id",
            record_id=metric_id,
            allowed=(
                "business_name", "description", "synonyms",
                "aggregation_type", "is_excluded", "is_confirmed",
            ),
            bool_fields=("is_excluded", "is_confirmed"),
            data=data,
            user=user,
            not_found="Metric not found."
        )

    @staticmethod
    def _patch(
        table: str,
        id_column: str,
        record_id: str,
        allowed: tuple,
        bool_fields: tuple,
        data: dict,
        user: dict,
        not_found: str
    ):
        # `table`, `id_column` and `allowed` are module constants chosen by the
        # two callers above, never caller input, so interpolating them into the
        # statement introduces no injection path. Every value is bound.
        assignments = []
        params = {
            "record_id": record_id,
            "updated_by": user["employee_id"]
        }

        for field in allowed:
            if data.get(field) is None:
                continue

            value = data[field]

            if field == "synonyms" and isinstance(value, (list, tuple)):
                value = ", ".join(str(t).strip() for t in value if str(t).strip())
            elif field in bool_fields:
                value = 1 if value else 0
            elif isinstance(value, str):
                value = value.strip()

            assignments.append(f"{field} = :{field}")
            params[field] = value

        if not assignments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No configurable fields were supplied."
            )

        assignments.append("updated_at = GETDATE()")
        assignments.append("updated_by = :updated_by")

        statement = (
            f"UPDATE {table} SET "
            + ", ".join(assignments)
            + f" WHERE {id_column} = :record_id"
        )

        with engine.begin() as conn:
            result = conn.execute(text(statement), params)

            if result.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=not_found
                )

        return {"message": "Configuration updated."}


# ---------------------------------------------------------------------------
# Suggestions
#
# THE STEP 8 SEAM.
#
# Gate 2 Step 8 - semantic/config_suggester.py, which profiles each column and
# asks a model what it means - is implemented. This module STARTS a run and
# reads back what it stored; the fixture below survives only so the screens
# render on a connection that has never been profiled.
#
# Nothing here is a second implementation of Step 8. There is no profiling, no
# model call and no classification logic in this module - only invoking the
# service that does that, and reading the shape it produced.
# ---------------------------------------------------------------------------

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test",
    "fixtures",
    "semantic_suggestions.json"
)


class SuggestionService:

    # Retained only so an unreviewed session still behaves if the store is
    # empty. Rejections now persist in semantic_suggestion_evidence.review_status
    # (migration 007) and survive a restart.
    _rejected: set = set()

    @staticmethod
    def _stored_suggestions(connection_id: str) -> dict:
        """
        Read suggestions produced by the Step 8 service.

        Generating them costs a profiling pass and several model calls - minutes
        for three tables - so the result is stored (migration 007) and read back
        here. Regenerating on every page load would hang the screen.
        """
        query = """
            SELECT proposal_json, column_name, review_status
            FROM semantic_suggestion_evidence
            WHERE connection_id = :connection_id
              AND proposal_json IS NOT NULL
            ORDER BY table_name, column_name
        """

        tables, columns = [], []
        with engine.connect() as conn:
            for row in conn.execute(text(query), {"connection_id": connection_id}):
                try:
                    suggestion = json.loads(row[0])
                except (TypeError, ValueError):
                    continue

                suggestion["review_status"] = row[2]
                suggestion["is_confirmed"] = row[2] == "CONFIRMED"
                suggestion["rejected"] = row[2] == "REJECTED"

                (columns if row[1] is not None else tables).append(suggestion)

        return {"table_suggestions": tables, "column_suggestions": columns}

    @staticmethod
    def _naming(
        proposal: dict,
        existing_synonyms: Optional[str] = None,
        is_edited: bool = False
    ) -> dict:
        """
        The naming fields a confirmation should apply.

        Confirming used to write only the aggregation, role and flags, leaving
        business_name as whatever auto-discovery generated - so a reviewer
        accepted "Current Year Sales" and the configuration still read "C Y".
        Naming a column in business language is the main thing an administrator
        is here to do, and it was being silently discarded.

        Synonyms arrive as a list and are stored comma separated, matching the
        existing convention on these tables. When reviewer edits are present,
        their synonym list is authoritative and replaces previous synonyms
        (allowing deletions and changes). Unedited proposals merge additively.
        """
        naming = {}

        business_name = (proposal.get("business_name") or "").strip()
        if business_name:
            naming["business_name"] = business_name

        description = (proposal.get("description") or "").strip()
        if description or is_edited:
            naming["description"] = description

        proposed = proposal.get("synonyms")
        if isinstance(proposed, str):
            proposed = [t.strip() for t in proposed.split(",") if t.strip()]
        elif not isinstance(proposed, (list, tuple)):
            proposed = []

        if is_edited:
            seen = set()
            terms = []
            for term in proposed:
                term = str(term).strip()
                if term and term.lower() not in seen:
                    seen.add(term.lower())
                    terms.append(term)
            naming["synonyms"] = ", ".join(terms)
        else:
            merged, seen = [], set()
            for term in list(str(existing_synonyms or "").split(",")) + list(proposed):
                term = str(term).strip()
                if term and term.lower() not in seen:
                    seen.add(term.lower())
                    merged.append(term)

            if merged:
                naming["synonyms"] = ", ".join(merged)

        return naming

    @staticmethod
    def _mark_reviewed(
        suggestion_id: str,
        status_value: str,
        user: Optional[dict] = None,
        note: Optional[str] = None,
        updated_proposal: Optional[dict] = None
    ) -> None:
        """
        Record the outcome on the stored suggestion (migration 007).

        Confirming writes the configuration itself, which is what matters, but
        without this the suggestion stays PENDING and the review screen keeps
        offering a Confirm button for work already done - so a reviewer cannot
        tell what they have already been through.
        """
        with engine.begin() as conn:
            if updated_proposal is not None:
                row = conn.execute(text("""
                    SELECT proposal_json FROM semantic_suggestion_evidence
                    WHERE suggestion_id = :suggestion_id
                """), {"suggestion_id": suggestion_id}).fetchone()

                if row and row[0]:
                    try:
                        s_data = json.loads(row[0])
                        s_data["proposal"] = updated_proposal
                        s_data["review_status"] = status_value
                        s_data["is_confirmed"] = (status_value == "CONFIRMED")
                        new_json = json.dumps(s_data)
                        conn.execute(text("""
                            UPDATE semantic_suggestion_evidence
                            SET proposal_json = :proposal_json,
                                review_status = :status_value,
                                reviewed_by   = :reviewed_by,
                                reviewed_at   = GETDATE(),
                                review_note   = :note
                            WHERE suggestion_id = :suggestion_id
                        """), {
                            "proposal_json": new_json,
                            "status_value": status_value,
                            "reviewed_by": (user or {}).get("employee_id"),
                            "note": note,
                            "suggestion_id": suggestion_id,
                        })
                        return
                    except Exception as ex:
                        logger.warning("Could not update proposal_json in _mark_reviewed: %s", ex)

            conn.execute(text("""
                UPDATE semantic_suggestion_evidence
                SET review_status = :status_value,
                    reviewed_by   = :reviewed_by,
                    reviewed_at   = GETDATE(),
                    review_note   = :note
                WHERE suggestion_id = :suggestion_id
            """), {
                "status_value": status_value,
                "reviewed_by": (user or {}).get("employee_id"),
                "note": note,
                "suggestion_id": suggestion_id,
            })

    @staticmethod
    def _load_suggestions() -> dict:
        """
        Stored suggestions when there are any, the development fixture otherwise.

        The fixture uses a made-up table name, so confirming anything from it
        fails with "not registered as a metric or a dimension". It remains only
        so the screens render before the suggester has ever been run.
        """
        connection = ConnectionService.get_active_connection_global()
        if connection:
            stored = SuggestionService._stored_suggestions(connection["connection_id"])
            if stored["table_suggestions"] or stored["column_suggestions"]:
                return stored

        if not os.path.exists(_FIXTURE_PATH):
            return {"table_suggestions": [], "column_suggestions": []}

        with open(_FIXTURE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def source_status() -> dict:
        """
        Tell the caller where suggestions came from.

        The screens use this to state plainly when they are showing development
        fixture data, so nobody mistakes it for a real profiling run - and the
        fixture's table names do not exist, so nothing from it can be confirmed.
        """
        connection = ConnectionService.get_active_connection_global()
        stored_count = 0

        if connection:
            with engine.connect() as conn:
                stored_count = conn.execute(text("""
                    SELECT COUNT(*) FROM semantic_suggestion_evidence
                    WHERE connection_id = :connection_id AND proposal_json IS NOT NULL
                """), {"connection_id": connection["connection_id"]}).scalar() or 0

        if stored_count:
            return {
                "source": "suggester",
                "step_8_implemented": True,
                "available": True,
                "message": (
                    f"{stored_count} suggestions from a profiling run against the "
                    "live connection. Nothing is applied until it is confirmed."
                )
            }

        return {
            "source": "fixture",
            "step_8_implemented": True,
            "available": os.path.exists(_FIXTURE_PATH),
            "message": (
                "No suggestions have been generated for this connection yet, so "
                "development fixture data is shown. Its table names are not real, "
                "so confirming from it will fail. Generate suggestions to replace it."
            )
        }

    # ------------------------------------------------------------------
    # Starting a run
    #
    # A run takes minutes - a profiling scan plus seven paced model calls per
    # table - so it cannot be done inside the request. It runs on a background
    # thread and the caller polls generation_status().
    #
    # The progress report lives in module state rather than a table because
    # startup.sh runs a single uvicorn process with no --workers: there is
    # exactly one of these, so a poll cannot land on a worker that knows
    # nothing about the run. If the deployment ever grows workers this has to
    # move into the database.
    #
    # The work itself is already durable either way. ConfigSuggester writes
    # every suggestion to semantic_suggestion_evidence, so a restart mid-run
    # loses the progress report, not the suggestions.
    # ------------------------------------------------------------------

    _generation_lock = threading.Lock()
    _generation: dict = {
        "status": "IDLE",
        "started_at": None,
        "finished_at": None,
        "started_by": None,
        "table_names": None,
        "use_model": None,
        "table_count": None,
        "column_count": None,
        "error": None,
    }

    @staticmethod
    def start_generation(
        table_names: Optional[List[str]] = None,
        use_model: bool = True,
        user: Optional[dict] = None
    ) -> dict:
        """
        Profile the active connection and propose configuration for it.

        Returns immediately with the run state; the run continues in the
        background. Existing suggestions are replaced table by table as it
        goes, and a review decision on an unchanged proposal is preserved
        (see ConfigSuggester._persist_evidence).
        """
        connection = ConnectionService.get_active_connection_global()

        if not connection:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No active database connection, so there is nothing to "
                    "profile. Activate a connection first."
                )
            )

        with SuggestionService._generation_lock:
            if SuggestionService._generation["status"] == "RUNNING":
                # Two concurrent runs would delete and reinsert the same rows
                # against each other. Refuse rather than interleave.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A suggestion run is already in progress. Wait for it "
                        "to finish before starting another."
                    )
                )

            SuggestionService._generation = {
                "status": "RUNNING",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "started_by": (user or {}).get("employee_id"),
                "table_names": list(table_names) if table_names else None,
                "use_model": use_model,
                "table_count": None,
                "column_count": None,
                "error": None,
            }

        threading.Thread(
            target=SuggestionService._run_generation,
            args=(
                connection["connection_id"],
                connection.get("company_id"),
                list(table_names) if table_names else None,
                use_model,
            ),
            name="semantic-suggestion-run",
            daemon=True,
        ).start()

        return SuggestionService.generation_status()

    @staticmethod
    def _run_generation(
        connection_id: str,
        company_id: Optional[str],
        table_names: Optional[List[str]],
        use_model: bool
    ) -> None:
        """The background half of start_generation. Never raises."""

        # Imported here rather than at module scope: config_suggester pulls in
        # the LLM stack, and this module is imported by the router at startup.
        from semantic.config_suggester import ConfigSuggester

        try:
            result = ConfigSuggester.suggest(
                connection_id=connection_id,
                table_names=table_names,
                company_id=company_id,
                persist_evidence=True,
                use_model=use_model,
            )
            outcome = {
                "status": "SUCCEEDED",
                "table_count": len(result.get("table_suggestions", [])),
                "column_count": len(result.get("column_suggestions", [])),
                "error": None,
            }
            logger.info(
                "Suggestion run finished: %d table and %d column suggestions.",
                outcome["table_count"], outcome["column_count"]
            )
        except Exception as exc:
            logger.exception("Suggestion run failed.")
            outcome = {
                "status": "FAILED",
                "table_count": None,
                "column_count": None,
                "error": str(exc),
            }

        with SuggestionService._generation_lock:
            SuggestionService._generation.update(outcome)
            SuggestionService._generation["finished_at"] = (
                datetime.now(timezone.utc).isoformat()
            )

    @staticmethod
    def generation_status() -> dict:
        """
        Where the last or current run got to.

        elapsed_seconds is computed here rather than stored so it keeps moving
        while a run is in progress and freezes once it ends.
        """
        with SuggestionService._generation_lock:
            state = dict(SuggestionService._generation)

        started = state.get("started_at")
        if started:
            ended = state.get("finished_at")
            finish = (
                datetime.fromisoformat(ended) if ended
                else datetime.now(timezone.utc)
            )
            state["elapsed_seconds"] = round(
                (finish - datetime.fromisoformat(started)).total_seconds(), 1
            )
        else:
            state["elapsed_seconds"] = None

        state["running"] = state["status"] == "RUNNING"

        if state["status"] == "RUNNING":
            scope = (
                ", ".join(state["table_names"]) if state["table_names"]
                else "every table on the connection"
            )
            state["message"] = (
                f"Profiling {scope}. This takes a few minutes per table when a "
                f"model is being asked; nothing changes on screen until it "
                f"finishes."
            )
        elif state["status"] == "SUCCEEDED":
            state["message"] = (
                f"{state['column_count']} column and {state['table_count']} "
                f"table suggestions written. Review decisions on proposals that "
                f"did not change were kept."
            )
        elif state["status"] == "FAILED":
            state["message"] = f"The run failed: {state['error']}"
        else:
            state["message"] = "No suggestion run has been started yet."

        return state

    @staticmethod
    def list_suggestions(
        table_name: Optional[str] = None,
        include_rejected: bool = False
    ) -> dict:

        data = SuggestionService._load_suggestions()

        tables = data.get("table_suggestions", [])
        columns = data.get("column_suggestions", [])

        if table_name:
            tables = [
                s for s in tables
                if s["table_name"].lower() == table_name.lower()
            ]
            columns = [
                s for s in columns
                if s["table_name"].lower() == table_name.lower()
            ]

        def is_rejected(item: dict) -> bool:
            # The store is authoritative; the in-memory set only covers
            # suggestions that have no stored row, such as fixture data.
            return (
                item.get("review_status") == "REJECTED"
                or item["suggestion_id"] in SuggestionService._rejected
            )

        if not include_rejected:
            tables = [s for s in tables if not is_rejected(s)]
            columns = [s for s in columns if not is_rejected(s)]

        for s in tables + columns:
            s["rejected"] = is_rejected(s)

        # Genuinely awaiting review, not merely present. A confirmed suggestion
        # stays in the list so a reviewer can see what they decided, but calling
        # it pending would misreport how much work is left.
        pending = [
            s for s in tables + columns
            if s.get("review_status", "PENDING") == "PENDING"
        ]

        return {
            "source_status": SuggestionService.source_status(),
            "table_suggestions": tables,
            "column_suggestions": columns,
            "pending_count": len(pending),
            "reviewed_count": (len(tables) + len(columns)) - len(pending)
        }

    @staticmethod
    def get_suggestion(suggestion_id: str) -> dict:
        data = SuggestionService._load_suggestions()

        everything = (
            data.get("table_suggestions", [])
            + data.get("column_suggestions", [])
        )

        for s in everything:
            if s["suggestion_id"] == suggestion_id:
                s["rejected"] = suggestion_id in SuggestionService._rejected
                return s

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suggestion '{suggestion_id}' not found."
        )

    @staticmethod
    def confirm_suggestion(
        connection_id: str,
        suggestion_id: str,
        edited_proposal: Optional[dict],
        user: dict
    ) -> dict:
        """
        Accept a suggestion and write it into the real configuration tables.

        This genuinely persists: the configuration tables exist. Reviewer edits
        override the machine's proposal field by field, because correcting a
        proposal before accepting it is the point of the review step.
        """

        suggestion = SuggestionService.get_suggestion(suggestion_id)

        proposal = dict(suggestion.get("proposal", {}))

        if edited_proposal:
            proposal.update(
                {k: v for k, v in edited_proposal.items() if v is not None}
            )

        is_table_suggestion = "column_name" not in suggestion

        if is_table_suggestion:
            result = SuggestionService._confirm_table(
                connection_id=connection_id,
                suggestion=suggestion,
                proposal=proposal,
                edited_proposal=edited_proposal,
                user=user
            )
        else:
            result = SuggestionService._confirm_column(
                connection_id=connection_id,
                suggestion=suggestion,
                proposal=proposal,
                user=user,
                is_edited=bool(edited_proposal)
            )

        # Only after the configuration write succeeded. Marking first would
        # leave a suggestion recorded as confirmed when nothing was applied.
        SuggestionService._mark_reviewed(
            suggestion_id, "CONFIRMED", user, updated_proposal=proposal if edited_proposal else None
        )
        result["review_status"] = "CONFIRMED"
        return result

    @staticmethod
    def _confirm_table(
        connection_id: str,
        suggestion: dict,
        proposal: dict,
        edited_proposal: Optional[dict],
        user: dict
    ) -> dict:

        table_name = suggestion["table_name"]

        domain_id = proposal.get("domain_id")

        # A table suggestion names its domain in business terms. Resolve it to
        # an id, and fail rather than inventing a domain: creating business
        # areas silently is how a typo becomes a second domain nobody notices.
        domain_name = proposal.get("domain_name")

        if not domain_id and domain_name:
            with engine.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT domain_id
                        FROM semantic_domains
                        WHERE connection_id = :connection_id
                          AND LOWER(domain_name) = LOWER(:domain_name)
                    """),
                    {
                        "connection_id": connection_id,
                        "domain_name": domain_name
                    }
                ).fetchone()

            if not row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"The suggestion binds this table to domain "
                        f"'{domain_name}', which does not exist yet. Create "
                        "the domain first, then confirm."
                    )
                )

            domain_id = row[0]

        result = TableConfigService.upsert_table_config(
            connection_id=connection_id,
            table_name=table_name,
            data={
                "domain_id": domain_id,
                "temporal_strategy": proposal.get("temporal_strategy"),
                "date_column": proposal.get("date_column"),
                "month_column": proposal.get("month_column"),
                "month_sort_column": proposal.get("month_sort_column"),
                # `or 1`, not a get() default: the key is present and set to
                # None whenever the model could not tell, and a get() default
                # only fires on a missing key. The column is NOT NULL, so the
                # None went all the way to the driver.
                "fiscal_year_start_month":
                    proposal.get("fiscal_year_start_month") or 1,
                "is_confirmed": True
            },
            user=user
        )

        mappings = suggestion.get("snapshot_mappings", [])

        if edited_proposal and edited_proposal.get("snapshot_mappings"):
            mappings = edited_proposal["snapshot_mappings"]

        warnings = []

        if mappings:
            for m in mappings:
                m["is_confirmed"] = True

            mapping_result = SnapshotMappingService.replace_mappings(
                connection_id=connection_id,
                table_name=table_name,
                mappings=mappings,
                user=user
            )

            warnings = mapping_result.get("warnings", [])

        return {
            "message": f"Table configuration for '{table_name}' confirmed.",
            "config_id": result.get("config_id"),
            "snapshot_mappings_written": len(mappings),
            "warnings": warnings,
            "persisted": True
        }

    @staticmethod
    def _create_config_row(
        connection_id: str,
        table_name: str,
        column_name: str,
        target_table: str,
        proposal: dict,
        user: dict
    ) -> str:
        """
        Create the registry row a suggestion targets when discovery never made
        one, and return its id.

        Only the identifying columns are written here. Everything the reviewer
        can change - business name, synonyms, description, role, exclusion,
        confirmation - is applied immediately afterwards by the ordinary update
        path in _confirm_column, so there is exactly one place that interprets
        a proposal.

        The technical name follows discovery's own convention
        (column_name.lower() with spaces underscored) so that a row created
        here is indistinguishable from one discovery would have made, and
        source stays 'AUTO' because the column did come from the schema - the
        administrator confirmed an interpretation of it, they did not invent it.
        """
        new_id = str(uuid.uuid4())
        technical_name = (column_name or "").lower().replace(" ", "_")

        # business_name is NOT NULL; the update path overwrites it a moment
        # later, but the insert still needs a value that is never blank.
        business_name = proposal.get("business_name") or column_name

        params = {
            "id": new_id,
            "connection_id": connection_id,
            "technical_name": technical_name,
            "business_name": business_name,
            "table_name": table_name,
            "column_name": column_name,
            "created_by": user.get("employee_id"),
            "updated_by": user.get("employee_id"),
        }

        if target_table == "semantic_metrics":
            # A metric row needs an aggregation. SUM is the discovery default
            # and is corrected by the update path when the proposal names one.
            params["aggregation_type"] = proposal.get("aggregation_type") or "SUM"
            insert_sql = """
                INSERT INTO semantic_metrics (
                    metric_id, connection_id, metric_name, business_name,
                    table_name, column_name, aggregation_type,
                    source, is_active, created_by, updated_by
                ) VALUES (
                    :id, :connection_id, :technical_name, :business_name,
                    :table_name, :column_name, :aggregation_type,
                    'AUTO', 1, :created_by, :updated_by
                )
            """
        else:
            insert_sql = """
                INSERT INTO semantic_dimensions (
                    dimension_id, connection_id, dimension_name, business_name,
                    table_name, column_name,
                    source, is_active, created_by, updated_by
                ) VALUES (
                    :id, :connection_id, :technical_name, :business_name,
                    :table_name, :column_name,
                    'AUTO', 1, :created_by, :updated_by
                )
            """

        with engine.begin() as conn:
            conn.execute(text(insert_sql), params)

        logger.info(
            "Created %s row for %s.%s from a confirmed suggestion; discovery "
            "had not registered it.",
            target_table, table_name, column_name
        )

        return new_id

    @staticmethod
    def _confirm_column(
        connection_id: str,
        suggestion: dict,
        proposal: dict,
        user: dict,
        is_edited: bool = False
    ) -> dict:

        table_name = suggestion["table_name"]
        column_name = suggestion["column_name"]

        classification = proposal.get("classification")

        # EXCLUDED is not a third place to store a column. It means: leave the
        # row where it already lives and switch it off. That keeps the audit
        # trail - you can still see that DocMonth was discovered as a metric.
        target_table = (
            suggestion.get("target", {}).get("config_table")
            or (
                "semantic_metrics"
                if classification == "MEASURE"
                else "semantic_dimensions"
            )
        )

        with engine.begin() as conn:

            metric = conn.execute(
                text("""
                    SELECT metric_id, synonyms
                    FROM semantic_metrics
                    WHERE connection_id = :connection_id
                      AND table_name = :table_name
                      AND column_name = :column_name
                """),
                {
                    "connection_id": connection_id,
                    "table_name": table_name,
                    "column_name": column_name
                }
            ).fetchone()

            dimension = conn.execute(
                text("""
                    SELECT dimension_id, synonyms
                    FROM semantic_dimensions
                    WHERE connection_id = :connection_id
                      AND table_name = :table_name
                      AND column_name = :column_name
                """),
                {
                    "connection_id": connection_id,
                    "table_name": table_name,
                    "column_name": column_name
                }
            ).fetchone()

        if not metric and not dimension:
            # The suggester profiles every physical column; discovery registers
            # only a subset of them. Gate 2 Step 12 taught discovery to skip a
            # constant column such as PBI_OUTSTANDING_ENES_SUMMARY.CreatedDate
            # (one distinct value across 95,613 rows) and an identifier such as
            # transid (99.4% unique). Both are correctly kept out of the
            # registry, and both are still profiled and proposed - so every
            # proposal for a column in that gap used to be unconfirmable, and
            # sat in the review queue forever.
            #
            # The proposal already says what to do about it: its target carries
            # action UPSERT and current.exists is false. Only the insert half
            # was missing. Creating the row records the administrator's
            # decision instead of leaving it implied by an absent row, which is
            # ambiguous - absent means either "never examined" or "deliberately
            # rejected", and the queue cannot distinguish them.
            #
            # This is safe only because the runtime now honours configuration
            # (Gate 3 P0): a row created here with is_excluded = 1 or
            # dimension_role = INTERNAL is recorded but never offered to a
            # question. Discovery's prune spares it too, since Step 12 already
            # excludes confirmed and excluded rows from pruning.
            new_id = SuggestionService._create_config_row(
                connection_id=connection_id,
                table_name=table_name,
                column_name=column_name,
                target_table=target_table,
                proposal=proposal,
                user=user
            )

            # Match the shape the SELECTs above return, (id, synonyms), so the
            # update path below runs unchanged.
            if target_table == "semantic_metrics":
                metric = (new_id, None)
            else:
                dimension = (new_id, None)

        written = []

        is_excluded = bool(proposal.get("is_excluded"))

        if metric:
            metric_data = {
                "is_confirmed": True,
                "is_excluded":
                    is_excluded or classification in ("DIMENSION", "EXCLUDED")
            }
            metric_data.update(
                SuggestionService._naming(proposal, metric[1], is_edited=is_edited)
            )

            if proposal.get("aggregation_type"):
                metric_data["aggregation_type"] = proposal["aggregation_type"]

            ColumnConfigService.update_metric_config(
                metric_id=str(metric[0]),
                data=metric_data,
                user=user
            )

            written.append("semantic_metrics")

        if dimension:
            dimension_data = {
                "dimension_role": proposal.get("dimension_role"),
                "is_confirmed": True,
                "is_excluded":
                    is_excluded or classification in ("MEASURE", "EXCLUDED")
            }
            dimension_data.update(
                SuggestionService._naming(proposal, dimension[1], is_edited=is_edited)
            )

            ColumnConfigService.update_dimension_config(
                dimension_id=str(dimension[0]),
                data=dimension_data,
                user=user
            )

            written.append("semantic_dimensions")

        notes = []

        if classification == "DIMENSION" and metric and not dimension:
            notes.append(
                f"'{column_name}' is registered only as a metric. It has been "
                "excluded as a measure, but no dimension row exists to promote "
                "it into. Re-run discovery, or add the dimension manually."
            )

        if classification == "MEASURE" and dimension and not metric:
            notes.append(
                f"'{column_name}' is registered only as a dimension. It has "
                "been excluded as a dimension, but no metric row exists to "
                "promote it into. Re-run discovery, or add the metric manually."
            )

        return {
            "message": f"Suggestion for '{column_name}' confirmed.",
            "target_config_table": target_table,
            "tables_written": written,
            "notes": notes,
            "persisted": True
        }

    @staticmethod
    def reject_suggestion(
        suggestion_id: str,
        reason: Optional[str],
        user: Optional[dict] = None
    ) -> dict:
        """
        Decline a suggestion, durably.

        This used to be held in a set in memory and lost on restart, because
        nothing could store it. Migration 007 added review_status to the
        suggestion store, so a rejection now survives - a reviewer can work
        through ninety-odd columns across more than one sitting without the
        ones they already declined reappearing.
        """

        SuggestionService.get_suggestion(suggestion_id)

        SuggestionService._mark_reviewed(suggestion_id, "REJECTED", user, reason)

        # Kept in step for the current process, so a rejection is reflected even
        # if the suggestion came from the fixture and has no stored row.
        SuggestionService._rejected.add(suggestion_id)

        return {
            "message": f"Suggestion '{suggestion_id}' rejected.",
            "persisted": True,
            "reason": reason,
            "review_status": "REJECTED"
        }


# ---------------------------------------------------------------------------
# Column configuration state
#
# Served from this module rather than extended onto SemanticService.get_metrics
# because semantic_service.py is a shared file. The existing /semantic/metrics
# and /semantic/dimensions endpoints keep returning exactly what they returned
# before; the screens merge this alongside by id.
# ---------------------------------------------------------------------------

class ColumnStateService:

    @staticmethod
    def list_column_state(connection_id: str) -> dict:
        with engine.connect() as conn:

            metrics = conn.execute(
                text("""
                    SELECT
                        metric_id,
                        table_name,
                        column_name,
                        aggregation_type,
                        is_excluded,
                        is_confirmed
                    FROM semantic_metrics
                    WHERE connection_id = :connection_id
                """),
                {"connection_id": connection_id}
            ).fetchall()

            dimensions = conn.execute(
                text("""
                    SELECT
                        dimension_id,
                        table_name,
                        column_name,
                        dimension_role,
                        is_excluded,
                        is_confirmed
                    FROM semantic_dimensions
                    WHERE connection_id = :connection_id
                """),
                {"connection_id": connection_id}
            ).fetchall()

        return {
            "metrics": [_row_to_dict(r) for r in metrics],
            "dimensions": [_row_to_dict(r) for r in dimensions]
        }
