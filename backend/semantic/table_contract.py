"""
A compact, per-table semantic contract for the SQL-generation prompt.

WHY THIS EXISTS

A pre-aggregated snapshot table cannot be described by its column names alone.
`CY`, `PYTD` and `PY` look like ordinary numeric columns, so a generator that
sees only the schema will happily add `WHERE createddate BETWEEN ...` to a
figure that is already periodized - which is exactly what production did:

    SELECT SUM(PYTD) ... WHERE createddate >= DATEFROMPARTS(...)

Right column, corrupted number. The missing information is not in the schema,
it is in the semantic configuration, and this module is the one place that
turns that configuration into words the generator can act on.

WHERE THE FACTS COME FROM

Every statement below is read from configuration - semantic_table_config and
semantic_snapshot_mapping, through the existing SnapshotConfigLoader. Nothing
is hardcoded: no column names, no fiscal months, no table names. If an
administrator changes the fiscal year or rebinds a period column, the contract
changes with it and no code is touched.

WHY IT IS EMITTED ONLY FOR SNAPSHOT TABLES

A table with a real row-level business date needs none of this, and pasting the
rules everywhere would both cost tokens and invite the generator to apply
snapshot reasoning to tables where ordinary date filtering is correct.
"""
from typing import List, Optional


_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _month_name(month: int) -> str:
    try:
        return _MONTH_NAMES[int(month) - 1]
    except Exception:
        return str(month)


def _fiscal_span(start_month: int) -> str:
    start = int(start_month or 1)
    end = 12 if start == 1 else start - 1
    return "%s to %s" % (_month_name(start), _month_name(end))


def _cols(bindings) -> str:
    return ", ".join(sorted(b.column_name for b in bindings))


def _describe(binding, start_month: int) -> str:
    """One period column, in business language, from its binding alone."""
    span = _fiscal_span(start_month)
    first = _month_name(start_month)
    last = span.split(" to ")[-1]

    if binding.period_offset == 0:
        when = "the current fiscal year"
    elif binding.period_offset == 1:
        when = "the previous fiscal year"
    else:
        when = "the fiscal year %d years ago" % binding.period_offset

    if binding.period_scope == "TO_DATE":
        covers = "%s 1 of %s up to the current month - a part-year figure" % (first, when)
    else:
        covers = "all of %s (%s to %s)" % (when, first, last)

    kind = "quantity" if binding.measure_kind == "QUANTITY" else "value"
    return "- %s : %s (%s)" % (binding.column_name, covers, kind)


def build_table_contract(connection_id: Optional[str], table_names) -> str:
    """
    The contract for whichever selected tables are snapshot-configured.

    Returns "" when no selected table is a snapshot table, so the caller can
    drop the whole section from the prompt rather than emit an empty heading.
    """
    if not connection_id or not table_names:
        return ""

    from semantic.temporal.snapshot_config import SnapshotConfigLoader

    blocks: List[str] = []

    for table_name in table_names:
        if not table_name:
            continue
        try:
            config = SnapshotConfigLoader.for_table(connection_id, table_name)
        except Exception:
            continue

        if not config or not config.is_configured or not config.bindings:
            continue

        start_month = config.fiscal_year_start_month or 1
        ordered = sorted(
            config.bindings,
            key=lambda b: (b.measure_kind, b.period_offset, b.period_scope),
        )
        measures = "\n".join(_describe(b, start_month) for b in ordered)

        to_date_now = [b for b in config.bindings
                       if b.period_offset == 0 and b.period_scope == "TO_DATE"]
        prev_to_date = [b for b in config.bindings
                        if b.period_offset == 1 and b.period_scope == "TO_DATE"]
        prev_full = [b for b in config.bindings
                     if b.period_offset == 1 and b.period_scope == "FULL"]

        rules: List[str] = []
        for kind, noun in (("VALUE", "amounts"), ("QUANTITY", "quantities")):
            now = [b for b in to_date_now if b.measure_kind == kind]
            full_prev = [b for b in prev_full if b.measure_kind == kind]
            td_prev = [b for b in prev_to_date if b.measure_kind == kind]
            if not (now or full_prev or td_prev):
                continue

            rules.append("For %s:" % noun)
            if now:
                rules.append("  - \"this year\" / \"current year\" -> %s"
                             % _cols(now))
            if full_prev:
                rules.append("  - \"last year\" on its own, meaning the whole "
                             "previous year -> %s" % _cols(full_prev))
            if td_prev:
                rules.append("  - \"last year till date\" / \"LYTD\" / \"PYTD\" -> %s"
                             % _cols(td_prev))
            if now and td_prev:
                rules.append(
                    "  - comparing the current year WITH last year -> %s vs %s. "
                    "Never compare a part-year against a complete year: the "
                    "current year is still running, so the only honest "
                    "comparison is to-date against to-date. Use %s only when "
                    "the user explicitly asks for the FULL previous year."
                    % (_cols(now), _cols(td_prev),
                       _cols(full_prev) if full_prev else "the complete-year column"))
            elif now and full_prev and not td_prev:
                rules.append(
                    "  - there is no to-date column for the previous year here, "
                    "so a current-vs-last-year comparison would set a part year "
                    "against a whole one. Say so rather than reporting the "
                    "difference as if it were like for like.")

        trend = ""
        if config.month_column:
            order_col = config.month_sort_column or config.month_column
            months = _month_values(connection_id, table_name, config.month_column)
            month_note = ""
            if months:
                # The stored form matters. These values carry a sort prefix so
                # they order by fiscal month rather than alphabetically, so a
                # filter written as = 'August' matches nothing at all.
                month_note = (
                    "- %s values are stored exactly as: %s.\n"
                    "  Filter on the stored form, not on a bare month name.\n"
                    % (config.month_column, ", ".join("'%s'" % m for m in months))
                )
            trend = (
                "TREND AND MONTHLY BREAKDOWN\n"
                "- A trend, a monthly breakdown, or \"by month\" question groups by %s.\n"
                "- SELECT %s alongside the measure, GROUP BY %s, ORDER BY %s.\n"
                "- The period still decides WHICH measure column is summed; the "
                "month only decides how it is broken up.\n"
                "%s"
                % (config.month_column, config.month_column,
                   config.month_column, order_col, month_note)
            )

        blocks.append(
            "TABLE %s\n"
            "\n"
            "PURPOSE\n"
            "- A pre-aggregated summary. One row is already a total; there is no\n"
            "  invoice-level detail and no row-level business date.\n"
            "\n"
            "FISCAL CALENDAR\n"
            "- The fiscal year runs %s.\n"
            "\n"
            "PERIOD MEASURES - each column IS a period, already aggregated\n"
            "%s\n"
            "\n"
            "PERIOD SELECTION\n"
            "%s\n"
            "\n"
            "%s"
            "RESTRICTIONS\n"
            "- Do NOT add any date filter (WHERE on a date column) when using these\n"
            "  measures. The column already restricts the period; an extra date\n"
            "  filter double-restricts it and returns a wrong number.%s\n"
            "- Do NOT treat these columns as ordinary values to filter by date range.\n"
            "- Do NOT invent measures this table does not hold. There is no cost,\n"
            "  margin, target, forecast or pipeline column here; if the question\n"
            "  needs one, say so rather than deriving a substitute."
            % (
                table_name,
                _fiscal_span(start_month),
                measures,
                "\n".join(rules) if rules else "- Use the configured period columns above.",
                trend + "\n" if trend else "",
                _no_date_column_note(config, connection_id, table_name),
            )
        )

    if not blocks:
        return ""

    return "\n\n".join(blocks)


def _month_values(connection_id, table_name, month_column, limit: int = 24):
    """
    The month column's real stored values, in their configured order.

    Read from the same value index the resolver uses. Bounded: a column with
    more entries than a year of months is not a month column, and listing it
    would cost tokens for nothing.
    """
    try:
        from semantic.value_provider import DbDimensionValueProvider

        provider = DbDimensionValueProvider(connection_id=connection_id)
        values = {
            v.value for v in provider._values()
            if (v.column_name or "").lower() == (month_column or "").lower()
            and (v.table_name or "").lower() == (table_name or "").lower()
            and v.value
        }
    except Exception:
        return []

    if not values or len(values) > limit:
        return []
    return sorted(values)


def _no_date_column_note(config, connection_id, table_name) -> str:
    """
    Name the trap column explicitly when the table has no business date.

    Saying "do not filter by date" is weaker than saying "createddate is an ETL
    timestamp, not a business date": the generator reached for that column
    precisely because it looked like a date, and only the configuration knows
    it is not one.
    """
    try:
        from sqlalchemy import text
        from database import engine

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT date_column FROM semantic_table_config "
                    "WHERE connection_id = :c AND UPPER(table_name) = UPPER(:t)"
                ),
                {"c": str(connection_id), "t": str(table_name)},
            ).fetchone()
    except Exception:
        return ""

    if row is not None and not row[0]:
        return (
            " This table has no configured business date column, so any\n"
            "  date-looking column on it (for example an ETL or created timestamp)\n"
            "  is metadata and must never be used to filter business periods."
        )
    return ""
