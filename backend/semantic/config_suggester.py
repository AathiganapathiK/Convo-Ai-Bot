"""
Gate 2 Step 8 - the configuration suggestion service.

Profiles every column in a datasource and asks a model what each one means, so
that migration 004's configuration tables can be filled by review rather than by
somebody typing meaning for a hundred and twenty columns.

WHY A MODEL AND NOT A RULE
    Auto-discovery decides a column is a measure with
    "is it numeric, and does its name avoid id/key/flag/code". That is why
    DocMonth, InvMonth, Sno, OrderNo and Docnum are all registered as things to
    add up. No name-based rule fixes this, because whether a numeric column is a
    quantity or an identifier is not present in its name or its type. It is
    present in its values: twelve distinct entries reading "A April", "B May"
    is a month label, and a value that increments once per row is a key.
    So the profile goes to a model, and the model's answer goes to a human.

WHAT THIS MODULE DOES NOT DO
    It does not decide anything. Every proposal it produces is unconfirmed, and
    nothing downstream may treat an unconfirmed proposal as authoritative. The
    evidence it records exists so a reviewer can disagree with it.

PRIVACY
    Sample values pass two gates before they are read.

    By cardinality: at or below SAMPLE_CARDINALITY_LIMIT distinct values a
    column is codes or categories - TN, A April, BANIANS - and samples are read.
    Above it the column holds names or identifiers and its values are never
    read.

    By name: any column whose name suggests it identifies a person is withheld
    however few values it has. Cardinality alone was not enough - RMNAME holds
    eight distinct values and every one of them is a real person's name.

    Withheld means never read from the database, so never sent to a model and
    never written to the evidence table. Only the column name, its type and its
    counts travel, and the reason is recorded so the review screen can explain
    the empty evidence box rather than looking broken.

OUTPUT CONTRACT
    suggest() returns exactly the shape consumed by
    semantic/config_service.py SuggestionService._load_suggestions():

        {"table_suggestions": [...], "column_suggestions": [...]}

    That shape is owned jointly with Step 9/10 and is mirrored by the
    development fixture at test/fixtures/semantic_suggestions.json. Changing it
    breaks the configuration screens.
"""

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from services.connection_manager import ConnectionManager
from services.connection_service import ConnectionService
from services.llm_execution_service import LLMExecutionService

logger = logging.getLogger(__name__)


# Vocabulary. Must match semantic/config_schema.py, which is what the API
# validates against - an unconstrained free-text role is how "TIME_LABEL" and
# "Time Label" become two different roles.
CLASSIFICATIONS = ("MEASURE", "DIMENSION", "EXCLUDED")
DIMENSION_ROLES = ("GROUPING", "TIME_LABEL", "IDENTIFIER", "INTERNAL")
TEMPORAL_STRATEGIES = ("SNAPSHOT", "DATE_COLUMN", "NONE")
MEASURE_KINDS = ("VALUE", "QUANTITY")
PERIOD_SCOPES = ("FULL", "TO_DATE")

# Purpose used for model routing. Falls back to a purpose that is definitely
# configured rather than failing, because an unrouted purpose would make the
# whole suggester unusable on a fresh install.
LLM_PURPOSE = "semantic_annotation"
LLM_PURPOSE_FALLBACK = "insight"


class ConfigSuggester:

    # At or below this many distinct values, sample values are read and sent to
    # the model. Above it they are withheld.
    #
    # Set at 500 rather than something tighter because personal data is now
    # caught by name, not by count, and this gate's remaining job is signal
    # quality. At 50 the product hierarchy was withheld for being marginally
    # over - ProdGrp1 has 56 values, ProdGrp2 261, ProdGrp3 386, KeyLine 263 -
    # and those are precisely the columns whose values tell the model what they
    # are. Customer codes (27,781 distinct) stay well above the line. Only
    # SAMPLE_SIZE values are ever read regardless of where this sits.
    SAMPLE_CARDINALITY_LIMIT = 500

    # Cardinality alone is not a sufficient privacy gate, and real data proved
    # it: RMNAME holds only eight distinct values, so it passed the limit above,
    # but those eight values are the names of eight real people. A small set of
    # personal names is still personal data. Any column whose name suggests it
    # identifies a person is withheld regardless of how few values it has.
    #
    # The model loses nothing that matters - "RMNAME, nvarchar, 8 distinct
    # values, withheld as personal names" is ample to conclude it is a person
    # dimension.
    PERSONAL_NAME_PATTERNS = (
        "name", "person", "employee", "staff", "contact", "customer", "party",
        "email", "mail", "phone", "mobile", "address", "user", "owner",
    )

    # How many rows to profile. Full-table scans on a fact table are slow and
    # unnecessary; cardinality and null rate are stable well before this.
    PROFILE_ROW_LIMIT = 50000

    # How many sample values to carry into the prompt and the evidence record.
    SAMPLE_SIZE = 8

    # Columns per model call. Asking about all 38 at once produced a reply that
    # was truncated mid-JSON and therefore unparseable - LLMExecutionService
    # exposes no max_tokens, so the only lever is to ask for less. Smaller
    # batches also get more considered answers. The table-level question is a
    # separate call.
    COLUMN_BATCH_SIZE = 6

    # Seconds to wait between model calls. The free Groq tier allows 8,000
    # tokens per minute, and a table needs seven calls; without pacing the last
    # of them is rejected with a 429 and the table-level answer - the snapshot
    # mapping, which is the most valuable output - is the one that gets lost.
    CALL_PACING_SECONDS = 6.0

    # A rate-limited call is retried this many times, honouring the wait the
    # provider asks for.
    RATE_LIMIT_RETRIES = 3

    # How much smaller a column's mean must be, against the largest column for
    # the same period, before it is read as counting things rather than
    # measuring money.
    #
    # Ten is deliberately loose. The real separation on the sales table is
    # roughly 280x - CY averages 4,404 rupees where CYQ averages 15.5 items -
    # so anything from about 5 upwards classifies this data identically. The
    # loose threshold is there so that a genuinely close pair is left alone
    # rather than guessed at.
    QUANTITY_MAGNITUDE_RATIO = 10.0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    @staticmethod
    def suggest(
        connection_id: Optional[str] = None,
        table_names: Optional[List[str]] = None,
        company_id: Optional[str] = None,
        persist_evidence: bool = True,
        use_model: bool = True,
    ) -> Dict[str, Any]:
        """
        Profile a datasource and propose configuration for it.

        connection_id    which datasource; the active one when omitted
        table_names      restrict to these tables; all of them when omitted
        persist_evidence write the profile and reasoning to
                         semantic_suggestion_evidence (migration 006)
        use_model        False profiles and returns proposals derived from the
                         profile alone, without calling a model. Useful for
                         testing the profiler without spending tokens, and as a
                         degraded mode when no model is reachable.

        Returns {"table_suggestions": [...], "column_suggestions": [...]}.
        """
        connection = ConnectionService.get_active_connection_global()
        if not connection:
            raise ValueError("No active database connection.")

        resolved_connection_id = connection_id or connection["connection_id"]

        # Model routing is scoped per company: FallbackService filters
        # llm_fallbacks on company_id, so passing None finds no model and the
        # whole run silently degrades to profile-only. When the caller does not
        # supply one - a standalone or admin run - take it from the datasource.
        resolved_company_id = company_id or connection.get("company_id")

        source_engine = ConnectionManager.source(connection=connection)

        tables = table_names or ConfigSuggester._list_tables(source_engine)
        current = ConfigSuggester._load_current_config(resolved_connection_id)

        table_suggestions: List[dict] = []
        column_suggestions: List[dict] = []

        for table_name in tables:
            try:
                profiles = ConfigSuggester._profile_table(source_engine, table_name)
            except Exception as exc:
                # One unreadable table must not abort the whole run.
                logger.warning("Could not profile %s: %s", table_name, exc)
                continue

            if not profiles:
                continue

            verdicts = {}
            if use_model:
                try:
                    verdicts = ConfigSuggester._ask_model(
                        table_name, profiles, resolved_company_id
                    )
                except Exception as exc:
                    logger.warning(
                        "Model call failed for %s (%s); falling back to profile-only proposals.",
                        table_name, exc
                    )

            column_suggestions.extend(
                ConfigSuggester._build_column_suggestions(
                    table_name, profiles, verdicts, current
                )
            )
            table_suggestions.append(
                ConfigSuggester._build_table_suggestion(
                    table_name, profiles, verdicts, current
                )
            )

        result = {
            "table_suggestions": table_suggestions,
            "column_suggestions": column_suggestions,
        }

        if persist_evidence:
            try:
                ConfigSuggester._persist_evidence(resolved_connection_id, result)
            except Exception as exc:
                # Evidence is for the review screen. Losing it must not lose the
                # suggestions themselves.
                logger.error("Could not persist suggestion evidence: %s", exc)

        return result

    # ------------------------------------------------------------------
    # Profiling
    # ------------------------------------------------------------------

    @staticmethod
    def _list_tables(source_engine) -> List[str]:
        with source_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
            )).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def _profile_table(source_engine, table_name: str) -> List[dict]:
        """
        One profile per column: type, distinct count, null rate, and - only when
        cardinality allows - a few sample values.
        """
        with source_engine.connect() as conn:
            columns = conn.execute(text(
                "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = :t ORDER BY ORDINAL_POSITION"
            ), {"t": table_name}).fetchall()

            if not columns:
                return []

            # Profiled over the whole table, not a TOP-N sample. An earlier
            # version counted distinct values over the first N rows while
            # sampling values from the whole table, which produced evidence that
            # contradicted itself - a column reporting one distinct value while
            # displaying three samples. Worse, cardinality is the privacy gate:
            # a column with 7,000 distinct values overall but few in the first N
            # rows would have had its values read and sent. Correctness of that
            # gate outweighs the cost of a scan on tables this size.
            row_count = conn.execute(text(
                f"SELECT COUNT(*) FROM [{table_name}]"
            )).scalar() or 0

            profiles = []
            for column_name, data_type in columns:
                profile = {
                    "column_name": column_name,
                    "data_type": data_type,
                    "row_count_profiled": row_count,
                    "distinct_count": None,
                    "null_fraction": None,
                    "samples": [],
                    "samples_withheld": False,
                    "samples_withheld_reason": None,
                }

                try:
                    stats = conn.execute(text(
                        f"SELECT COUNT(DISTINCT [{column_name}]), "
                        f"       SUM(CASE WHEN [{column_name}] IS NULL THEN 1 ELSE 0 END), "
                        f"       COUNT(*) "
                        f"FROM [{table_name}]"
                    )).fetchone()
                    distinct_count, null_count, sampled_rows = (
                        stats[0] or 0, stats[1] or 0, stats[2] or 0
                    )
                    profile["distinct_count"] = distinct_count
                    profile["null_fraction"] = (
                        round(null_count / sampled_rows, 4) if sampled_rows else None
                    )
                except Exception as exc:
                    # Some types cannot be counted distinctly (text, image, xml).
                    logger.debug("No stats for %s.%s: %s", table_name, column_name, exc)
                    profiles.append(profile)
                    continue

                ConfigSuggester._gate_samples(conn, table_name, profile)
                profiles.append(profile)

        return profiles

    @staticmethod
    def _gate_samples(conn, table_name: str, profile: dict) -> None:
        """
        Read sample values only for low-cardinality columns.

        This is the privacy boundary. A column with tens of thousands of
        distinct values is a name or an identifier; its values are not read, so
        they cannot be sent to a model or written to the evidence table.
        """
        distinct_count = profile["distinct_count"]
        column_name = profile["column_name"]
        lowered = column_name.lower()

        matched = next(
            (pat for pat in ConfigSuggester.PERSONAL_NAME_PATTERNS if pat in lowered),
            None,
        )
        if matched:
            profile["samples_withheld"] = True
            profile["samples_withheld_reason"] = (
                f"Column name contains '{matched}', so it may identify a person. "
                f"Values were not read, regardless of cardinality"
                + (f" ({distinct_count:,} distinct)." if distinct_count is not None else ".")
            )
            return

        if distinct_count is None:
            profile["samples_withheld"] = True
            profile["samples_withheld_reason"] = (
                "Column type does not support a distinct count, so cardinality "
                "could not be established and values were not sampled."
            )
            return

        if distinct_count > ConfigSuggester.SAMPLE_CARDINALITY_LIMIT:
            # A high-cardinality NUMERIC column gets a range instead of silence.
            #
            # Withholding numbers outright cost accuracy on the columns that
            # matter most: with its values hidden, the model read the name "PY",
            # decided it meant "previous year", and classified a column full of
            # rupees as a year label. Nine core sales and quantity measures were
            # about to be turned into dimensions on the strength of their names.
            #
            # A range says what a name cannot - values running 0.50 to 4,500,000
            # are money, whereas a year label would run 2020 to 2026. It is also
            # LESS exposure than sampling: three aggregates reveal far less than
            # eight real transaction amounts.
            if ConfigSuggester._is_numeric(profile["data_type"]):
                if ConfigSuggester._describe_range(conn, table_name, profile):
                    return

            profile["samples_withheld"] = True
            profile["samples_withheld_reason"] = (
                f"High cardinality ({distinct_count:,} distinct values across "
                f"{profile['row_count_profiled']:,} rows) - values not sampled."
            )
            return

        try:
            rows = conn.execute(text(
                f"SELECT DISTINCT TOP {ConfigSuggester.SAMPLE_SIZE} [{column_name}] "
                f"FROM [{table_name}] WHERE [{column_name}] IS NOT NULL"
            )).fetchall()
            profile["samples"] = [str(r[0]) for r in rows]
        except Exception as exc:
            logger.debug("No samples for %s.%s: %s", table_name, column_name, exc)
            profile["samples_withheld"] = True
            profile["samples_withheld_reason"] = "Sample values could not be read."

    @staticmethod
    def _is_numeric(data_type: Optional[str]) -> bool:
        return any(
            t in (data_type or "").lower()
            for t in ("int", "decimal", "numeric", "money", "float", "real")
        )

    @staticmethod
    def _describe_range(conn, table_name: str, profile: dict) -> bool:
        """
        Replace sample values with min, max and mean for a numeric column.

        The descriptors go into the samples list rather than a new field, so the
        shape agreed with Step 9 and Step 10 is unchanged - the review screen
        renders them like any other evidence, and a reviewer sees the range that
        justified the proposal.
        """
        column_name = profile["column_name"]
        try:
            row = conn.execute(text(
                f"SELECT MIN([{column_name}]), MAX([{column_name}]), "
                f"AVG(CAST([{column_name}] AS FLOAT)) FROM [{table_name}]"
            )).fetchone()
        except Exception as exc:
            logger.debug("No range for %s.%s: %s", table_name, column_name, exc)
            return False

        if row is None or row[0] is None:
            return False

        low, high, mean = row
        profile["samples"] = [
            f"min: {low}",
            f"max: {high}",
            f"avg: {round(float(mean), 2) if mean is not None else 'n/a'}",
        ]
        # Kept as a number as well as a label. The samples list is display text
        # bound for a prompt and a screen; _resolve_measure_kinds needs to do
        # arithmetic on the mean, and parsing it back out of a string it just
        # formatted would be silly. Underscore-prefixed, so it stays out of the
        # evidence record like _is_range does.
        profile["_avg"] = float(mean) if mean is not None else None
        profile["samples_withheld"] = False
        profile["samples_withheld_reason"] = None
        profile["_is_range"] = True
        return True

    # ------------------------------------------------------------------
    # Current configuration, so a proposal reads as a change not a fact
    # ------------------------------------------------------------------

    @staticmethod
    def _load_current_config(connection_id: str) -> dict:
        """
        What is registered today, keyed by (table, column) and by table.

        Without this the review screen shows an assertion. With it, the screen
        can show that InvMonth is a metric today and the proposal moves it.
        """
        platform = ConnectionManager.platform()
        columns: Dict[tuple, dict] = {}
        tables: Dict[str, dict] = {}

        with platform.connect() as conn:
            for row in conn.execute(text(
                "SELECT table_name, column_name, business_name, is_excluded "
                "FROM semantic_metrics WHERE connection_id = :c"
            ), {"c": connection_id}):
                columns[(row[0], row[1])] = {
                    "exists": True,
                    "config_table": "semantic_metrics",
                    "classification": "MEASURE",
                    "business_name": row[2],
                    "is_excluded": bool(row[3]),
                }

            for row in conn.execute(text(
                "SELECT table_name, column_name, business_name, is_excluded "
                "FROM semantic_dimensions WHERE connection_id = :c"
            ), {"c": connection_id}):
                key = (row[0], row[1])
                # A column registered as both is a real defect worth surfacing,
                # but the dimension registration is the more specific one.
                columns[key] = {
                    "exists": True,
                    "config_table": "semantic_dimensions",
                    "classification": "DIMENSION",
                    "business_name": row[2],
                    "is_excluded": bool(row[3]),
                }

            for row in conn.execute(text(
                "SELECT t.table_name, d.domain_name, t.temporal_strategy, "
                "       t.month_column, t.month_sort_column, t.fiscal_year_start_month "
                "FROM semantic_table_config t "
                "LEFT JOIN semantic_domains d ON d.domain_id = t.domain_id "
                "WHERE t.connection_id = :c"
            ), {"c": connection_id}):
                tables[row[0]] = {
                    "exists": True,
                    "domain_name": row[1],
                    "temporal_strategy": row[2],
                    "month_column": row[3],
                    "month_sort_column": row[4],
                    "fiscal_year_start_month": row[5],
                }

        return {"columns": columns, "tables": tables}

    # ------------------------------------------------------------------
    # The model call
    # ------------------------------------------------------------------

    @staticmethod
    def _ask_model(table_name: str, profiles: List[dict], company_id) -> dict:
        """
        Annotate a table. Returns {column_name: verdict} plus a "__table__" entry.

        Columns are asked about in batches and the table-level temporal question
        is asked separately, because a single call covering every column
        overflowed the reply and came back as truncated, unparseable JSON. A
        batch that fails is skipped rather than aborting the table - those
        columns fall through to a profile-only proposal, which is marked as such.
        """
        verdicts: dict = {}
        batch_size = ConfigSuggester.COLUMN_BATCH_SIZE

        for start in range(0, len(profiles), batch_size):
            batch = profiles[start:start + batch_size]
            try:
                raw = ConfigSuggester._call(
                    ConfigSuggester._build_column_prompt(table_name, batch), company_id
                )
                parsed = ConfigSuggester._parse_model_output(raw)
                verdicts.update(parsed.get("columns") or {})
            except Exception as exc:
                logger.warning(
                    "Column batch %d-%d of %s failed: %s",
                    start, start + len(batch), table_name, exc
                )
            time.sleep(ConfigSuggester.CALL_PACING_SECONDS)

        try:
            raw = ConfigSuggester._call(
                ConfigSuggester._build_table_prompt(table_name, profiles), company_id
            )
            verdicts["__table__"] = (
                ConfigSuggester._parse_model_output(raw).get("table") or {}
            )
        except Exception as exc:
            logger.warning("Table-level call for %s failed: %s", table_name, exc)
            verdicts["__table__"] = {}

        if not any(k for k in verdicts if k != "__table__") and not verdicts["__table__"]:
            raise RuntimeError("No usable model output for this table.")

        return verdicts

    @staticmethod
    def _call(prompt: str, company_id) -> str:
        """One model call, paced and retried past rate limits."""
        last_error = None

        for attempt in range(ConfigSuggester.RATE_LIMIT_RETRIES + 1):
            try:
                return ConfigSuggester._call_once(prompt, company_id)
            except Exception as exc:
                last_error = exc
                wait = ConfigSuggester._rate_limit_wait(exc)
                if wait is None or attempt == ConfigSuggester.RATE_LIMIT_RETRIES:
                    raise
                logger.info(
                    "Rate limited; waiting %.1fs before retry %d.",
                    wait, attempt + 1
                )
                time.sleep(wait)

        raise last_error if last_error else RuntimeError("Model call failed.")

    @staticmethod
    def _rate_limit_wait(exc: Exception) -> Optional[float]:
        """
        Seconds to wait if this looks like a rate limit, else None.

        The provider states how long to wait in the error text; honour it rather
        than guessing, and add a margin so the retry does not land on the edge
        of the window.
        """
        message = str(exc)
        if "rate_limit" not in message.lower() and "429" not in message:
            return None
        match = re.search(r"try again in ([0-9.]+)s", message, re.IGNORECASE)
        return float(match.group(1)) + 1.0 if match else 15.0

    @staticmethod
    def _call_once(prompt: str, company_id) -> str:
        response = None
        for purpose in (LLM_PURPOSE, LLM_PURPOSE_FALLBACK):
            try:
                response = LLMExecutionService.execute(
                    purpose=purpose,
                    messages=[{"role": "user", "content": prompt}],
                    company_id=company_id,
                )
                if response:
                    break
            except Exception as exc:
                logger.debug("Purpose %s unavailable: %s", purpose, exc)

        if not response:
            raise RuntimeError("No model available for semantic annotation.")

        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                return getattr(message, "content", "") or ""
        return ""

    @staticmethod
    def _column_lines(profiles: List[dict]) -> str:
        lines = []
        for p in profiles:
            if p["samples_withheld"]:
                label = "samples"
                sample_text = f"(values not read - {p['samples_withheld_reason']})"
            elif p.get("_is_range"):
                # Individual values were not read; these are aggregates.
                label = "value range"
                sample_text = ", ".join(p["samples"])
            else:
                label = "samples"
                sample_text = ", ".join(
                    repr(v) for v in p["samples"][:ConfigSuggester.SAMPLE_SIZE]
                )
            # Show the uniqueness ratio rather than making the model divide.
            # Asked to compare 132,955 distinct against 2,238,958 rows it
            # concluded "close to row count" - it is 6% - and excluded four core
            # sales measures as identifiers on that arithmetic. Stating the
            # percentage removes the mistake entirely.
            distinct = p["distinct_count"]
            rows = p["row_count_profiled"]
            if distinct is not None and rows:
                uniqueness = f"{(distinct / rows) * 100:.2f}% of rows are unique"
            else:
                uniqueness = "uniqueness unknown"

            lines.append(
                f"- {p['column_name']} | type={p['data_type']} "
                f"| distinct={p['distinct_count']} of {rows} rows ({uniqueness}) "
                f"| null_rate={p['null_fraction']} "
                f"| {label}: {sample_text}"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_column_prompt(table_name: str, profiles: List[dict]) -> str:
        return f"""You are annotating columns of a database table so business users can query it in plain language.

TABLE: {table_name}

COLUMNS:
{ConfigSuggester._column_lines(profiles)}

For EACH column decide:
- classification: MEASURE (a quantity worth summing), DIMENSION (something to group or filter by), or EXCLUDED (must not be offered to business users - identifiers, load timestamps, duplicated columns)
- business_name: what a business person would call it
- description: one short sentence
- synonyms: other words a person might use, as a list of strings
- dimension_role: GROUPING, TIME_LABEL, IDENTIFIER or INTERNAL
- aggregation_type: SUM, AVG, COUNT, MIN, MAX or null - only for MEASURE
- confidence: 0 to 1
- reasoning: one sentence citing the evidence you used

Judge from the VALUES, not the name. Use the stated uniqueness percentage; do not compute it yourself. Above roughly 95% the column is an identifier and summing it yields a meaningless figure. Well below that it is not an identifier, however many distinct values it has - a monetary column in a two-million-row table can hold a hundred thousand distinct amounts and still be an ordinary measure. Text values that read as month names are a period label. A column with a single distinct value across millions of rows is a load timestamp, not a business date.

Values withheld are not a reason to exclude. A column whose values were not read because they may name a person is still an ordinary grouping dimension: the business asks for sales by party and by regional manager, so those columns must be available to group by. Classify such a column DIMENSION with dimension_role GROUPING unless it holds a key or a code rather than a name. Reserve EXCLUDED for true identifiers - keys, codes, row numbers - along with load timestamps and duplicated columns.

Where a VALUE RANGE is given instead of samples, use it. A column running from 0.50 to 4,500,000 holds amounts and is a measure, however its name reads. A year or period label would run only from about 2000 to 2100, and a month from 1 to 12. Never conclude that a column contains a period merely because its name abbreviates one.

Return ONLY valid JSON, no prose, no code fences, and keep every string short:
{{"columns": {{"COLUMN_NAME": {{"classification": "...", "business_name": "...", "description": "...", "synonyms": [], "dimension_role": "...", "aggregation_type": null, "confidence": 0.0, "reasoning": "..."}}}}}}"""

    @staticmethod
    def _inventory_entry(profile: dict) -> str:
        """
        One column for the table-level prompt: name, type, cardinality, and the
        magnitudes where they were measured.
        """
        base = (
            f"{profile['column_name']}({profile['data_type']},"
            f"d={profile['distinct_count']}"
        )
        if profile.get("_is_range"):
            # _describe_range wrote "min: x", "max: y", "avg: z" into samples.
            base += "," + ",".join(profile["samples"]).replace(": ", "=")
        return base + ")"

    @staticmethod
    def _build_table_prompt(table_name: str, profiles: List[dict]) -> str:
        # Names, types, counts - and, for a numeric column, its magnitudes.
        #
        # The per-column detail went out in the column batches and repeating all
        # of it risks truncation again, but the magnitudes have to be here: this
        # is the call that decides measure_kind, and nothing else on this prompt
        # separates rupees from units. Without them the model read the trailing Q
        # of CYQ as decoration and labelled five quantity columns VALUE, which
        # collides them onto one unique key and silently drops four.
        inventory = ", ".join(
            ConfigSuggester._inventory_entry(p) for p in profiles
        )
        return f"""Decide how TIME works in this database table.

TABLE: {table_name}
COLUMNS: {inventory}

Decide:
- temporal_strategy: SNAPSHOT if each period lives in its own column (names like CY, PY, PYTD), DATE_COLUMN if periods are filtered from a real date column, NONE if there is no time dimension
- date_column: the real transaction date column, or null. A column with only one distinct value across every row is a load timestamp and is NOT a transaction date.
- month_column: the column holding a month label, or null
- month_sort_column: the column to ORDER BY for correct month sequence, or null. Not always the same column: a calendar month number sorts wrongly for a business whose year does not start in January, whereas a label carrying an explicit order prefix sorts correctly.
- fiscal_year_start_month: 1 to 12, or null if you cannot tell
- snapshot_mappings: for a SNAPSHOT table, one entry per period column:
    period_offset (0 = current, 1 = previous, 2 = two back, ...)
    measure_kind (VALUE for money or amount, QUANTITY for units or counts) - decide this from the magnitudes shown, not from the column name. Money and units for the SAME period differ by orders of magnitude: a column averaging thousands and reaching millions holds currency, while one for the same period averaging in the tens holds counts of items. A trailing Q or "qty" in the name is a hint, never the decision. Two entries that share period_offset, measure_kind and period_scope collide and all but one is discarded, so where several columns describe one period they must be told apart correctly here
    period_scope (FULL for a complete period, TO_DATE for one truncated to the same point as the current period)
    column_name
  The current period is still running, so a current-period column is TO_DATE. A prior period may appear in BOTH forms - a full-year column and a to-date column - and those are different figures. Never merge them; comparing a part-year against a full year misstates performance badly.
- confidence: 0 to 1
- reasoning: one or two sentences

Return ONLY valid JSON, no prose, no code fences:
{{"table": {{"temporal_strategy": "...", "date_column": null, "month_column": null, "month_sort_column": null, "fiscal_year_start_month": null, "snapshot_mappings": [], "confidence": 0.0, "reasoning": "..."}}}}"""

    @staticmethod
    def _parse_model_output(raw: str) -> dict:
        text_body = (raw or "").strip()
        if text_body.startswith("```"):
            text_body = text_body.split("```")[1] if "```" in text_body[3:] else text_body[3:]
            if text_body.lstrip().startswith("json"):
                text_body = text_body.lstrip()[4:]
        start = text_body.find("{")
        if start == -1:
            return {}

        # raw_decode stops at the end of the first complete object, so a reply
        # containing two concatenated objects parses instead of failing with
        # "Extra data". Slicing to the last brace would span both and break.
        try:
            parsed, _ = json.JSONDecoder().raw_decode(text_body[start:])
        except json.JSONDecodeError as exc:
            logger.warning("Model returned unparseable JSON: %s", exc)
            return {}
        if not isinstance(parsed, dict):
            return {}

        # Returned as the model shaped it - {"columns": {...}} or {"table": {...}}.
        # Callers unwrap. An earlier version unwrapped here as well, so
        # _ask_model asked for "columns" on an already-unwrapped dict, got None,
        # and merged nothing: every model answer was silently discarded and
        # every column fell through to a profile-only proposal.
        return parsed

    # ------------------------------------------------------------------
    # Assembling the agreed output shape
    # ------------------------------------------------------------------

    @staticmethod
    def _build_column_suggestions(
        table_name: str, profiles: List[dict], verdicts: dict, current: dict
    ) -> List[dict]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        suggested_by = f"llm:{LLM_PURPOSE}" if verdicts else "profile-only"
        out = []

        for profile in profiles:
            column_name = profile["column_name"]
            verdict = verdicts.get(column_name) or ConfigSuggester._fallback_verdict(profile)

            classification = ConfigSuggester._clamp(
                verdict.get("classification"), CLASSIFICATIONS, "DIMENSION"
            )
            role = ConfigSuggester._clamp(
                verdict.get("dimension_role"), DIMENSION_ROLES, None
            )
            is_excluded = classification == "EXCLUDED"

            # EXCLUDED is a decision about visibility, not about which table the
            # row lives in, so it keeps whichever config table already holds it.
            existing = current["columns"].get((table_name, column_name))
            if classification == "MEASURE":
                config_table = "semantic_metrics"
            elif classification == "DIMENSION":
                config_table = "semantic_dimensions"
            else:
                config_table = (
                    existing["config_table"] if existing else "semantic_dimensions"
                )

            out.append({
                "suggestion_id": f"col-{uuid.uuid4().hex[:12]}",
                "table_name": table_name,
                "column_name": column_name,
                "target": {"config_table": config_table, "action": "UPSERT"},
                "proposal": {
                    "classification": classification,
                    "business_name": verdict.get("business_name") or column_name,
                    "description": verdict.get("description"),
                    "synonyms": verdict.get("synonyms") or [],
                    "dimension_role": role,
                    "is_excluded": is_excluded,
                    "aggregation_type": (
                        verdict.get("aggregation_type") if classification == "MEASURE" else None
                    ),
                },
                "current": existing or {
                    "exists": False,
                    "config_table": None,
                    "classification": None,
                    "business_name": None,
                    "is_excluded": False,
                },
                "evidence": {
                    "data_type": profile["data_type"],
                    "distinct_count": profile["distinct_count"],
                    "null_fraction": profile["null_fraction"],
                    "samples": profile["samples"],
                    "samples_withheld": profile["samples_withheld"],
                    "samples_withheld_reason": profile["samples_withheld_reason"],
                    "row_count_profiled": profile["row_count_profiled"],
                },
                "confidence": ConfigSuggester._clamp_confidence(verdict.get("confidence")),
                "reasoning": verdict.get("reasoning"),
                "is_confirmed": False,
                "suggested_at": now,
                "suggested_by": suggested_by,
            })

        return out

    @staticmethod
    def _build_table_suggestion(
        table_name: str, profiles: List[dict], verdicts: dict, current: dict
    ) -> dict:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        verdict = verdicts.get("__table__") or {}

        strategy = ConfigSuggester._clamp(
            verdict.get("temporal_strategy"), TEMPORAL_STRATEGIES, None
        )

        mappings = []
        for m in (verdict.get("snapshot_mappings") or []):
            column_name = m.get("column_name")
            if not column_name:
                continue
            try:
                offset = int(m.get("period_offset"))
            except (TypeError, ValueError):
                continue
            if offset < 0:
                continue
            mappings.append({
                "period_offset": offset,
                # No default here. Defaulting a missing answer to VALUE is how a
                # model that simply omitted the field ended up asserting that a
                # quantity column holds money; _resolve_measure_kinds below
                # decides it from the evidence instead.
                "measure_kind": ConfigSuggester._clamp(
                    m.get("measure_kind"), MEASURE_KINDS, None
                ),
                "period_scope": ConfigSuggester._clamp(
                    m.get("period_scope"), PERIOD_SCOPES, "FULL"
                ),
                "column_name": column_name,
            })

        # The magnitudes decide quantity against value, not the model and not
        # the column name; then no two mappings may claim the same key.
        ConfigSuggester._resolve_measure_kinds(
            mappings, {p["column_name"]: p.get("_avg") for p in profiles}
        )

        for mapping in mappings:
            if mapping["measure_kind"] is None:
                # Nothing to compare it against and the model said nothing
                # usable. VALUE is the safer of the two: a money column read as
                # a count is merely mislabelled, whereas a count promoted into
                # the money slot displaces a real figure.
                mapping["measure_kind"] = "VALUE"

        mappings, mapping_conflicts = ConfigSuggester._drop_colliding_mappings(mappings)

        date_like = [
            p["column_name"] for p in profiles
            if "date" in (p["data_type"] or "").lower()
            or "date" in p["column_name"].lower()
        ]
        mapped = {m["column_name"] for m in mappings}
        period_like = [p["column_name"] for p in profiles if p["column_name"] in mapped]

        return {
            "suggestion_id": f"tbl-{uuid.uuid4().hex[:12]}",
            "table_name": table_name,
            "proposal": {
                "domain_name": verdict.get("domain_name"),
                "temporal_strategy": strategy,
                "date_column": verdict.get("date_column"),
                "month_column": verdict.get("month_column"),
                "month_sort_column": verdict.get("month_sort_column"),
                "fiscal_year_start_month": ConfigSuggester._clamp_month(
                    verdict.get("fiscal_year_start_month")
                ),
            },
            "current": current["tables"].get(table_name) or {
                "exists": False,
                "domain_name": None,
                "temporal_strategy": None,
                "month_column": None,
                "month_sort_column": None,
                "fiscal_year_start_month": None,
            },
            "snapshot_mappings": mappings,
            "evidence": {
                "date_like_columns": date_like,
                "period_like_columns": period_like,
                "reasoning": verdict.get("reasoning"),
                # Surfaced rather than swallowed: a dropped mapping means the
                # proposal does not cover every period column on the table.
                "mapping_conflicts": mapping_conflicts,
            },
            "confidence": ConfigSuggester._clamp_confidence(verdict.get("confidence")),
            "is_confirmed": False,
            "suggested_at": now,
            "suggested_by": f"llm:{LLM_PURPOSE}" if verdicts else "profile-only",
        }

    @staticmethod
    def _resolve_measure_kinds(mappings: List[dict], averages: dict) -> None:
        """
        Decide VALUE against QUANTITY from the magnitudes, in place.

        This does not ask the model, and it overrides the model where the two
        disagree, because the model has now got this wrong twice on the same
        table. It was told to judge by magnitude and it still labelled all five
        *Q columns VALUE - its own stated reasoning never mentions quantity at
        all. Meanwhile the arithmetic is not close: at period offset 0, CY
        averages 4,404 and CYQ averages 15.5.

        The cost of getting it wrong is not a bad label. Every mapping is keyed
        on (offset, measure_kind, period_scope), so calling CYQ a VALUE makes it
        collide with CY, and one of the two is discarded - which is how five
        quantity columns quietly vanished from the configuration.

        Only acts where there are at least two mapped columns for the same
        period to compare. A lone column has nothing to be smaller than, so it
        keeps whatever it already had.
        """
        by_offset: Dict[int, List[dict]] = {}
        for mapping in mappings:
            by_offset.setdefault(mapping["period_offset"], []).append(mapping)

        for group in by_offset.values():
            measured = [
                (mapping, abs(averages[mapping["column_name"]]))
                for mapping in group
                if averages.get(mapping["column_name"]) is not None
            ]

            if len(measured) < 2:
                continue

            largest = max(value for _, value in measured)
            if not largest:
                continue

            for mapping, value in measured:
                decided = (
                    "QUANTITY"
                    if value * ConfigSuggester.QUANTITY_MAGNITUDE_RATIO <= largest
                    else "VALUE"
                )

                if decided != mapping["measure_kind"]:
                    logger.info(
                        "Reading %s as %s rather than %s: mean %.2f against %.2f "
                        "for the same period.",
                        mapping["column_name"], decided, mapping["measure_kind"],
                        value, largest,
                    )

                mapping["measure_kind"] = decided

    @staticmethod
    def _drop_colliding_mappings(mappings: List[dict]) -> tuple:
        """
        One column per (period_offset, measure_kind, period_scope).

        The database enforces this with a unique key, so a proposal carrying two
        columns for one combination does not fail loudly - it is accepted, and
        the second row is rejected on save while the screen shows a tick. Better
        to drop the duplicate here and say so, so a reviewer can see that the
        proposal is incomplete rather than discovering it as a missing number
        months later.
        """
        seen, kept, conflicts = {}, [], []

        for mapping in mappings:
            key = (
                mapping["period_offset"],
                mapping["measure_kind"],
                mapping["period_scope"],
            )

            if key in seen:
                conflicts.append(
                    f"{mapping['column_name']} was dropped: it claims the same "
                    f"period, kind and scope as {seen[key]} "
                    f"(offset={key[0]}, {key[1]}, {key[2]})."
                )
                continue

            seen[key] = mapping["column_name"]
            kept.append(mapping)

        return kept, conflicts

    @staticmethod
    def _fallback_verdict(profile: dict) -> dict:
        """
        A proposal derived from the profile alone, used when no model answered.

        Deliberately timid: it only claims what the numbers alone support, and
        says so, so that a reviewer is not misled into rubber-stamping a guess
        that no model actually made.
        """
        distinct = profile["distinct_count"] or 0
        rows = profile["row_count_profiled"] or 0
        numeric = any(
            t in (profile["data_type"] or "").lower()
            for t in ("int", "decimal", "numeric", "money", "float", "real")
        )

        if rows and distinct >= rows * 0.95 and numeric:
            return {
                "classification": "EXCLUDED",
                "dimension_role": "IDENTIFIER",
                "confidence": 0.5,
                "reasoning": (
                    "Profile only, no model verdict. Distinct count is close to the "
                    "row count on a numeric column, which indicates an identifier."
                ),
            }

        return {
            "classification": "MEASURE" if numeric else "DIMENSION",
            "dimension_role": None if numeric else "GROUPING",
            "confidence": 0.3,
            "reasoning": (
                "Profile only, no model verdict. Classified from data type alone, "
                "which is exactly the weak signal this service exists to improve on. "
                "Review carefully."
            ),
        }

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    @staticmethod
    def _proposal_signature(proposal: dict) -> str:
        """
        The decision-bearing part of a proposal, as a stable string.

        Deliberately not the whole record. suggestion_id is a fresh uuid and
        suggested_at a fresh timestamp on every run, and the model's confidence
        and its prose reasoning move a little between runs even when it reaches
        the same conclusion. Comparing those would mean nothing ever matched and
        the preservation below would never fire. What a reviewer approves is the
        classification, the naming and the temporal mapping, so that - and only
        that - decides whether their decision still stands.
        """
        return json.dumps(
            {
                "target": proposal.get("target"),
                "proposal": proposal.get("proposal"),
                "snapshot_mappings": proposal.get("snapshot_mappings"),
            },
            sort_keys=True,
            default=str,
        )

    @staticmethod
    def _load_reviewed(connection_id: str, table_names: set) -> dict:
        """
        Stored proposals for these tables, keyed by (table, column).

        Read before the delete-and-reinsert below so a review decision can be
        carried across it.
        """
        if not table_names:
            return {}

        platform = ConnectionManager.platform()
        with platform.connect() as conn:
            stored_rows = conn.execute(text(
                "SELECT table_name, column_name, suggestion_id, proposal_json, "
                "       review_status, reviewed_by, reviewed_at, review_note "
                "FROM semantic_suggestion_evidence "
                "WHERE connection_id = :connection_id AND proposal_json IS NOT NULL"
            ), {"connection_id": connection_id}).fetchall()

        out = {}
        for r in stored_rows:
            if r[0] not in table_names:
                continue
            try:
                stored_proposal = json.loads(r[3])
            except (TypeError, ValueError):
                # An unreadable stored proposal cannot be compared, so it does
                # not preserve anything - the row is replaced as PENDING.
                continue
            out[(r[0], r[1])] = {
                "suggestion_id": r[2],
                "signature": ConfigSuggester._proposal_signature(stored_proposal),
                "review_status": r[4],
                "reviewed_by": r[5],
                "reviewed_at": r[6],
                "review_note": r[7],
            }
        return out

    @staticmethod
    def _persist_evidence(connection_id: str, result: dict) -> None:
        """
        Store each suggestion: the proposal itself, and the evidence behind it.

        Keyed on (connection, table, column), so re-running overwrites rather
        than accumulating. A table-level row carries column_name NULL.

        The proposal is stored whole as JSON (migration 007) because generating
        suggestions costs a profiling pass and several model calls - minutes,
        not milliseconds - so the review screen must read a stored result rather
        than regenerate one per page load.

        Re-running preserves a review decision where the proposal is unchanged.
        Resetting everything to PENDING was defensible in the abstract - a new
        proposal has not been reviewed - but in practice a regeneration returns
        the same answer for the great majority of 93 columns, and wiping the
        review of all of them to catch the handful that moved makes the reviewer
        start over each time. The configuration itself was never at risk; it
        lives in semantic_metrics and semantic_dimensions. What was lost was the
        record of which proposals a person had already worked through.
        """
        platform = ConnectionManager.platform()
        rows = []

        for s in result["column_suggestions"]:
            ev = s["evidence"]
            rows.append({
                "connection_id": connection_id,
                "table_name": s["table_name"],
                "column_name": s["column_name"],
                "suggestion_id": s["suggestion_id"],
                "proposal_json": json.dumps(s),
                "data_type": ev["data_type"],
                "distinct_count": ev["distinct_count"],
                "row_count_profiled": ev["row_count_profiled"],
                "null_fraction": ev["null_fraction"],
                "sample_values": json.dumps(ev["samples"]) if ev["samples"] else None,
                "samples_withheld": 1 if ev["samples_withheld"] else 0,
                "withheld_reason": ev["samples_withheld_reason"],
                "confidence": s["confidence"],
                "reasoning": s["reasoning"],
                "suggested_by": s["suggested_by"],
                "_source": s,
            })

        for s in result["table_suggestions"]:
            rows.append({
                "connection_id": connection_id,
                "table_name": s["table_name"],
                "column_name": None,
                "suggestion_id": s["suggestion_id"],
                "proposal_json": json.dumps(s),
                "data_type": None,
                "distinct_count": None,
                "row_count_profiled": None,
                "null_fraction": None,
                "sample_values": None,
                "samples_withheld": 0,
                "withheld_reason": None,
                "confidence": s["confidence"],
                "reasoning": (s["evidence"] or {}).get("reasoning"),
                "suggested_by": s["suggested_by"],
                "_source": s,
            })

        if not rows:
            return

        prior = ConfigSuggester._load_reviewed(
            connection_id, {r["table_name"] for r in rows}
        )

        for row in rows:
            source = row.pop("_source")
            stored = prior.get((row["table_name"], row["column_name"]))
            unchanged = (
                stored is not None
                and stored["signature"] == ConfigSuggester._proposal_signature(source)
            )

            if unchanged:
                # The same proposal keeps the same handle, so a link or a review
                # already holding the old suggestion_id still resolves to it.
                row["suggestion_id"] = stored["suggestion_id"] or row["suggestion_id"]
                row["review_status"] = stored["review_status"] or "PENDING"
                row["reviewed_by"] = stored["reviewed_by"]
                row["reviewed_at"] = stored["reviewed_at"]
                row["review_note"] = stored["review_note"]
            else:
                # A changed proposal genuinely has not been reviewed.
                row["review_status"] = "PENDING"
                row["reviewed_by"] = None
                row["reviewed_at"] = None
                row["review_note"] = None

            # These objects go straight back to the caller and on to the API, so
            # they have to agree with what is about to be written.
            source["suggestion_id"] = row["suggestion_id"]
            source["review_status"] = row["review_status"]
            source["is_confirmed"] = row["review_status"] == "CONFIRMED"
            row["proposal_json"] = json.dumps(source)

        with platform.begin() as conn:
            for row in rows:
                # The unique key spans a nullable column, so delete-then-insert
                # rather than MERGE, which treats NULL keys inconsistently.
                if row["column_name"] is None:
                    conn.execute(text(
                        "DELETE FROM semantic_suggestion_evidence "
                        "WHERE connection_id = :connection_id AND table_name = :table_name "
                        "AND column_name IS NULL"
                    ), {"connection_id": row["connection_id"], "table_name": row["table_name"]})
                else:
                    conn.execute(text(
                        "DELETE FROM semantic_suggestion_evidence "
                        "WHERE connection_id = :connection_id AND table_name = :table_name "
                        "AND column_name = :column_name"
                    ), {
                        "connection_id": row["connection_id"],
                        "table_name": row["table_name"],
                        "column_name": row["column_name"],
                    })

                conn.execute(text("""
                    INSERT INTO semantic_suggestion_evidence
                        (connection_id, table_name, column_name, suggestion_id, proposal_json,
                         data_type, distinct_count, row_count_profiled, null_fraction,
                         sample_values, samples_withheld, withheld_reason, confidence,
                         reasoning, suggested_by, review_status, reviewed_by, reviewed_at,
                         review_note)
                    VALUES
                        (:connection_id, :table_name, :column_name, :suggestion_id, :proposal_json,
                         :data_type, :distinct_count, :row_count_profiled, :null_fraction,
                         :sample_values, :samples_withheld, :withheld_reason, :confidence,
                         :reasoning, :suggested_by, :review_status, :reviewed_by, :reviewed_at,
                         :review_note)
                """), row)

        logger.info("Recorded evidence for %d suggestions.", len(rows))

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value, allowed, default):
        """Keep a model's answer inside the agreed vocabulary."""
        if isinstance(value, str) and value.strip().upper() in allowed:
            return value.strip().upper()
        return default

    @staticmethod
    def _clamp_confidence(value) -> Optional[float]:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _clamp_month(value) -> Optional[int]:
        try:
            month = int(value)
        except (TypeError, ValueError):
            return None
        return month if 1 <= month <= 12 else None
