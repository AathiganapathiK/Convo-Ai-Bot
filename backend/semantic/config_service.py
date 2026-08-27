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
import os
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text

from database import engine
from services.connection_service import ConnectionService


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
            allowed=("dimension_role", "is_excluded", "is_confirmed"),
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
            allowed=("aggregation_type", "is_excluded", "is_confirmed"),
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

            if field in bool_fields:
                value = 1 if value else 0

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
# Gate 2 Step 8 - the suggestion service that profiles each column and asks a
# model what it means - is not implemented. Until it is, suggestions are read
# from a development fixture so that the API and the review screens can be
# built and tested against the agreed shape.
#
# When Step 8 lands, only _load_suggestions() changes: it calls the suggestion
# service instead of reading the file. Route handlers, response shapes and the
# entire frontend stay as they are.
#
# Nothing here is a second implementation of Step 8. There is no profiling, no
# model call and no classification logic in this module - only reading a shape
# that something else produced.
# ---------------------------------------------------------------------------

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test",
    "fixtures",
    "semantic_suggestions.json"
)


class SuggestionService:

    # Rejections have nowhere to persist. Migration 004 records confirmation on
    # the configuration rows themselves, and a rejected suggestion has no
    # configuration row to mark. Persisting them needs the suggestion evidence
    # store that Step 8 proposes and that does not exist yet, so a rejection is
    # held in memory and is lost on restart. Every reject response says so.
    _rejected: set = set()

    @staticmethod
    def _load_suggestions() -> dict:
        if not os.path.exists(_FIXTURE_PATH):
            return {"table_suggestions": [], "column_suggestions": []}

        with open(_FIXTURE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def source_status() -> dict:
        """
        Tell the caller where suggestions came from.

        The screens use this to state plainly that they are showing development
        fixture data, so nobody mistakes it for a real profiling run.
        """

        available = os.path.exists(_FIXTURE_PATH)

        return {
            "source": "fixture",
            "step_8_implemented": False,
            "available": available,
            "message": (
                "Gate 2 Step 8 (suggestion service) is not implemented. "
                "Suggestions shown are development fixture data, not a "
                "profiling run against the live connection."
            )
        }

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

        if not include_rejected:
            tables = [
                s for s in tables
                if s["suggestion_id"] not in SuggestionService._rejected
            ]
            columns = [
                s for s in columns
                if s["suggestion_id"] not in SuggestionService._rejected
            ]

        for s in tables + columns:
            s["rejected"] = s["suggestion_id"] in SuggestionService._rejected

        return {
            "source_status": SuggestionService.source_status(),
            "table_suggestions": tables,
            "column_suggestions": columns,
            "pending_count": len(tables) + len(columns)
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
            return SuggestionService._confirm_table(
                connection_id=connection_id,
                suggestion=suggestion,
                proposal=proposal,
                edited_proposal=edited_proposal,
                user=user
            )

        return SuggestionService._confirm_column(
            connection_id=connection_id,
            suggestion=suggestion,
            proposal=proposal,
            user=user
        )

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
                "fiscal_year_start_month":
                    proposal.get("fiscal_year_start_month", 1),
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
    def _confirm_column(
        connection_id: str,
        suggestion: dict,
        proposal: dict,
        user: dict
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
                    SELECT metric_id
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
                    SELECT dimension_id
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Column '{table_name}.{column_name}' is not registered as "
                    "a metric or a dimension, so there is no row to confirm. "
                    "Run schema discovery for this connection first."
                )
            )

        written = []

        is_excluded = bool(proposal.get("is_excluded"))

        if metric:
            metric_data = {
                "is_confirmed": True,
                "is_excluded":
                    is_excluded or classification in ("DIMENSION", "EXCLUDED")
            }

            if proposal.get("aggregation_type"):
                metric_data["aggregation_type"] = proposal["aggregation_type"]

            ColumnConfigService.update_metric_config(
                metric_id=str(metric[0]),
                data=metric_data,
                user=user
            )

            written.append("semantic_metrics")

        if dimension:
            ColumnConfigService.update_dimension_config(
                dimension_id=str(dimension[0]),
                data={
                    "dimension_role": proposal.get("dimension_role"),
                    "is_confirmed": True,
                    "is_excluded":
                        is_excluded or classification in ("MEASURE", "EXCLUDED")
                },
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
    def reject_suggestion(suggestion_id: str, reason: Optional[str]) -> dict:
        """
        Mark a suggestion as rejected for this process only.

        There is deliberately no database write here. Nothing in migration 004
        can hold a rejection, and inventing a table for it is not this step's
        work. The response says plainly that it was not persisted so the screen
        can say the same rather than implying it saved.
        """

        SuggestionService.get_suggestion(suggestion_id)

        SuggestionService._rejected.add(suggestion_id)

        return {
            "message": f"Suggestion '{suggestion_id}' rejected for this session.",
            "persisted": False,
            "reason": reason,
            "limitation": (
                "Rejections are held in memory and are lost when the API "
                "restarts. Persisting them requires the suggestion evidence "
                "store from Gate 2 Step 8, which is not implemented."
            )
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
