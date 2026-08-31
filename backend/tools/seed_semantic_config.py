"""
Gate 2 Step 13 - enter the real semantic configuration.

Everything the suggester cannot know, written down once and applied the same
way to every environment.

WHY THIS IS A TOOL AND NOT A MIGRATION
--------------------------------------
This is data, not schema, and every row is keyed by connection_id - which is a
different GUID on the server and on a developer machine. A .sql migration
cannot express that; it would hardcode one environment's GUID and silently do
nothing on the other. So the connection is resolved at run time and the writes
go through the same services the API uses, which means the same validation and
the same audit columns as a human clicking Save.

WHY IT EXISTS AT ALL, WHEN THERE ARE SCREENS FOR THIS
-----------------------------------------------------
Roughly twenty fields, entered by hand, in the same way, on at least two
databases, and again after any reset. That is exactly the kind of work that is
done wrong once and then trusted forever. Written down here it is reviewable,
repeatable, and diffable.

WHAT IT DOES NOT DO
-------------------
It does not touch the suggestion review queue. Confirming machine proposals is
a human's job and belongs on the review screen; this tool only writes the facts
a human already established. The one exception is the column corrections at the
bottom, which fix classifications the model gets wrong for a reason we have
verified - see COLUMN_CORRECTIONS.

USAGE
-----
    python tools/seed_semantic_config.py              # show the plan, write nothing
    python tools/seed_semantic_config.py --apply      # write it
    python tools/seed_semantic_config.py --apply --as-user E1234

Idempotent: a second run reports "unchanged" for everything and writes nothing.
"""

import argparse
import os
import sys

# Same import dance as tools/run_migrations.py: the backend directory has to be
# importable before core.config or database are touched, so that running this
# as "python tools/seed_semantic_config.py" works as well as "-m tools.…".
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.config  # noqa: F401,E402  - selects and loads the runtime env file
from sqlalchemy import text  # noqa: E402

from database import engine  # noqa: E402
from services.connection_manager import ConnectionManager  # noqa: E402
from services.connection_service import ConnectionService  # noqa: E402
from semantic.config_service import (  # noqa: E402
    ColumnConfigService,
    DomainService,
    SnapshotMappingService,
    TableConfigService,
)


SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"
ORDER_PENDING = "PBI_ENES_ORDER_PENDING_SUMMARY"
RECEIVABLES = "PBI_OUTSTANDING_ENES_SUMMARY"


# ---------------------------------------------------------------------------
# 1. Domains - which business area each table serves
# ---------------------------------------------------------------------------

DOMAINS = [
    {
        "domain_name": "Sales",
        "business_name": "Sales",
        "synonyms": "revenue, turnover, billing, invoiced",
        "description": "Invoiced sales by region, party, product and month.",
    },
    {
        "domain_name": "Order Pending",
        "business_name": "Order Pending",
        "synonyms": "pending orders, open orders, order book, backlog, unshipped",
        "description": "Orders received but not yet delivered.",
    },
    {
        "domain_name": "Receivables",
        "business_name": "Receivables",
        "synonyms": "outstanding, debtors, collections, dues, ageing",
        "description": "Money invoiced and not yet collected, with ageing.",
    },
]


# ---------------------------------------------------------------------------
# 2. Table configuration - how time works on each table
#
# fiscal_year_start_month is 4 on all three: the business year runs April to
# March. This is never inferred. The data happens to agree - CY is non-zero
# only in months 4 to 8 - but a fiscal year is a decision, not a measurement,
# and a year that merely looked April-aligned in the data would be guessed
# wrong the moment a table had a quiet January.
#
# Sales is SNAPSHOT: each period lives in its own column (CY, PY, PYTD, ...)
# rather than being filtered from a date. Its month label is InvMonth, and
# InvMonth is ALSO its sort column - the prefix letter encodes fiscal order
# (A April, B May ... L March), so ordering the text sorts the fiscal year
# correctly. DocMonth would put January first, which is wrong for this
# business, and InvMonthS ("J [ JAN ]") carries no usable order.
#
# date_column is deliberately NULL on Sales. The only date-like column is
# createddate, which is an ETL load timestamp - the user has confirmed it must
# never be used for analysis, and it is indexed six times over by
# auto-discovery, which Step 12 will fix.
# ---------------------------------------------------------------------------

TABLES = [
    {
        "table_name": SALES,
        "domain_name": "Sales",
        "temporal_strategy": "SNAPSHOT",
        "date_column": None,
        "month_column": "InvMonth",
        "month_sort_column": "InvMonth",
        "fiscal_year_start_month": 4,
    },
    {
        "table_name": ORDER_PENDING,
        "domain_name": "Order Pending",
        "temporal_strategy": "DATE_COLUMN",
        "date_column": "DocDate",
        "month_column": "DocMonth",
        "month_sort_column": None,
        "fiscal_year_start_month": 4,
    },
    {
        "table_name": RECEIVABLES,
        "domain_name": "Receivables",
        "temporal_strategy": "DATE_COLUMN",
        "date_column": "Docdate",
        "month_column": None,
        "month_sort_column": None,
        "fiscal_year_start_month": 4,
    },
]


# ---------------------------------------------------------------------------
# 3. Snapshot mappings - which column holds which period
#
# This replaces SNAPSHOT_SALES_BINDINGS in semantic_plan_builder.py, which
# Step 11 deletes. That dictionary knew five columns; the table has eleven, and
# the six it did not know are where the wrong numbers come from.
#
# THE TRAP, verified against live data on 2026-08-27 and the reason
# period_scope exists at all:
#
#   CY   = 9,861,221,505  - current fiscal year, five months so far  (TO_DATE)
#   PY   = 26,418,229,830 - previous fiscal year, all twelve months  (FULL)
#   PYTD = 8,615,660,088  - previous fiscal year, the same five      (TO_DATE)
#
# CY against PY reads as a 63% collapse. CY against PYTD is 14.5% growth. Same
# question, same data, opposite answers - so a year-on-year comparison of a
# partial current year MUST resolve to the TO_DATE row for the prior period.
# That is only possible if both rows are configured, which is why they are both
# here and why replace_mappings refuses to save one without the other.
#
# The *Q columns are QUANTITY, not quarters. Settled by their magnitudes: CYQ
# runs 0 to 204,800 averaging 15, while CY reaches 16.8M averaging 4,404. One
# counts items, the other is rupees. There is no quarterly data in this table.
# ---------------------------------------------------------------------------

SALES_MAPPINGS = [
    # period_offset, measure_kind, period_scope, column_name
    (0, "VALUE", "TO_DATE", "CY"),
    (1, "VALUE", "FULL", "PY"),
    (1, "VALUE", "TO_DATE", "PYTD"),
    (2, "VALUE", "FULL", "PPY"),
    (3, "VALUE", "FULL", "PPPY"),
    (4, "VALUE", "FULL", "PPPPY"),

    (0, "QUANTITY", "TO_DATE", "CYQ"),
    (1, "QUANTITY", "FULL", "PYQ"),
    (2, "QUANTITY", "FULL", "PPYQ"),
    (3, "QUANTITY", "FULL", "PPPYQ"),
    (4, "QUANTITY", "FULL", "PPPPYQ"),
]


# ---------------------------------------------------------------------------
# 4. Column corrections
#
# A name column is a grouping dimension, not an identifier to be hidden.
#
# The suggester withholds the values of any column whose name suggests it
# identifies a person - RMNAME holds eight real people, Cardname holds party
# names - and the model reads that silence as suspicion and proposes EXCLUDED.
# But "sales by regional manager" and "sales by party" are two of the questions
# this system exists to answer. The prompt has been corrected so a regenerated
# proposal should now say GROUPING, and this makes the state right either way.
#
# Matched case-insensitively: the same column is RMNAME, Cardname, cardname and
# CardName across the three tables.
# ---------------------------------------------------------------------------

COLUMN_CORRECTIONS = {
    "RMNAME": {
        "dimension_role": "GROUPING",
        "is_excluded": False,
        "business_name": "Regional Manager",
        "synonyms": "RM, regional manager, manager, area manager",
    },
    "CARDNAME": {
        "dimension_role": "GROUPING",
        "is_excluded": False,
        "business_name": "Party",
        "synonyms": "party, customer, client, account, dealer",
    },
}


# ---------------------------------------------------------------------------
# Plan and apply
# ---------------------------------------------------------------------------

class Plan:
    """Collects what would change, so a dry run reads like a diff."""

    def __init__(self):
        self.actions = []
        self.problems = []

    def add(self, verb, what, detail=""):
        self.actions.append((verb, what, detail))

    def problem(self, what):
        self.problems.append(what)

    @property
    def changes(self):
        return [a for a in self.actions if a[0] != "unchanged"]

    def render(self):
        width = max((len(a[1]) for a in self.actions), default=0)
        for verb, what, detail in self.actions:
            print(f"  {verb:<9} {what:<{width}}  {detail}")

        if self.problems:
            print("\n  PROBLEMS")
            for p in self.problems:
                print(f"    - {p}")


def resolve_connection(connection_id):
    if connection_id:
        return connection_id

    connection = ConnectionService.get_active_connection_global()
    if not connection:
        sys.exit(
            "No active database connection, and no --connection-id given. "
            "Activate a connection or pass one explicitly."
        )

    print(
        f"Connection: {connection.get('connection_name')} "
        f"({connection['connection_id']})"
    )
    return connection["connection_id"]


def preflight_columns(connection_id, plan):
    """
    Every column this tool names must exist in the source database.

    A configuration that points at a column which is not there is worse than no
    configuration: it passes every CHECK constraint, saves cleanly, and then
    fails at query time in front of a user - or, for a snapshot mapping, quietly
    produces a wrong number instead of an error. The names below were read off
    the live schema, but a table can be rebuilt, so they are checked on every
    run rather than trusted.

    Case is reported but not treated as a failure: SQL Server resolves column
    names case-insensitively under the default collation, so PYTD and pytd are
    the same column. A mismatch is still worth printing, because the stored
    configuration is what a person reads later.
    """
    referenced = {
        SALES: (
            [column for _, _, _, column in SALES_MAPPINGS]
            + [t["month_column"] for t in TABLES if t["table_name"] == SALES]
            + [t["month_sort_column"] for t in TABLES if t["table_name"] == SALES]
        ),
        ORDER_PENDING: [
            t[field] for t in TABLES if t["table_name"] == ORDER_PENDING
            for field in ("date_column", "month_column", "month_sort_column")
        ],
        RECEIVABLES: [
            t[field] for t in TABLES if t["table_name"] == RECEIVABLES
            for field in ("date_column", "month_column", "month_sort_column")
        ],
    }

    connection = ConnectionService.get_active_connection_global()
    if not connection or connection["connection_id"] != connection_id:
        plan.problem(
            "Could not check the column names: the target connection is not "
            "the active one, so the source database was not opened."
        )
        return

    try:
        source = ConnectionManager.source(connection=connection)
        with source.connect() as conn:
            for table_name, columns in referenced.items():
                actual = {
                    row[0] for row in conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = :t"
                    ), {"t": table_name})
                }

                if not actual:
                    plan.problem(f"Table {table_name} was not found in the source database.")
                    continue

                by_lower = {a.lower(): a for a in actual}

                for column in [c for c in columns if c]:
                    match = by_lower.get(column.lower())
                    if not match:
                        plan.problem(
                            f"{table_name}.{column} does not exist in the source "
                            f"database. Nothing will be written."
                        )
                    elif match != column:
                        plan.problem(
                            f"{table_name}.{column} is spelled '{match}' in the "
                            f"source. Same column to SQL Server, but fix the "
                            f"spelling here so the stored configuration reads true."
                        )
    except Exception as exc:
        plan.problem(f"Could not check the column names against the source: {exc}")


def seed_domains(connection_id, user, plan, apply):
    existing = {
        d["domain_name"].lower(): d
        for d in DomainService.list_domains(connection_id)
    }
    ids = {}

    for spec in DOMAINS:
        current = existing.get(spec["domain_name"].lower())

        if not current:
            plan.add("create", f"domain {spec['domain_name']}", spec["business_name"])
            if apply:
                result = DomainService.create_domain(connection_id, spec, user)
                ids[spec["domain_name"]] = result["domain_id"]
            continue

        ids[spec["domain_name"]] = current["domain_id"]

        differs = [
            field for field in ("business_name", "synonyms", "description")
            if (current.get(field) or "") != (spec.get(field) or "")
        ]

        if differs:
            plan.add(
                "update", f"domain {spec['domain_name']}", "changed: " + ", ".join(differs)
            )
            if apply:
                DomainService.update_domain(current["domain_id"], spec, user)
        else:
            plan.add("unchanged", f"domain {spec['domain_name']}")

    return ids


def seed_tables(connection_id, domain_ids, user, plan, apply):
    current_by_name = {
        c["table_name"]: c
        for c in TableConfigService.list_table_configs(connection_id)
    }

    for spec in TABLES:
        domain_id = domain_ids.get(spec["domain_name"])

        if domain_id is None and not apply:
            # A dry run against empty tables has no domain ids yet, because
            # nothing was created. Say so rather than reporting a false diff.
            domain_id = "(pending domain creation)"

        data = {
            "domain_id": domain_id,
            "temporal_strategy": spec["temporal_strategy"],
            "date_column": spec["date_column"],
            "month_column": spec["month_column"],
            "month_sort_column": spec["month_sort_column"],
            "fiscal_year_start_month": spec["fiscal_year_start_month"],
            # A person decided these, so they are confirmed on arrival. Nothing
            # here came from a model.
            "is_confirmed": True,
        }

        current = current_by_name.get(spec["table_name"])
        summary = (
            f"{spec['temporal_strategy']}"
            f"{' date=' + spec['date_column'] if spec['date_column'] else ''}"
            f"{' month=' + spec['month_column'] if spec['month_column'] else ''}"
            f"{' sort=' + spec['month_sort_column'] if spec['month_sort_column'] else ''}"
            f" fy={spec['fiscal_year_start_month']}"
        )

        if not current:
            plan.add("create", f"table  {spec['table_name']}", summary)
        else:
            differs = [
                field for field in (
                    "temporal_strategy", "date_column", "month_column",
                    "month_sort_column", "fiscal_year_start_month",
                )
                if (current.get(field) or None) != (spec.get(field) or None)
            ]
            if current.get("domain_name") != spec["domain_name"]:
                differs.append("domain")

            if differs:
                plan.add(
                    "update", f"table  {spec['table_name']}",
                    summary + "  [changed: " + ", ".join(differs) + "]"
                )
            else:
                plan.add("unchanged", f"table  {spec['table_name']}", summary)
                continue

        if apply:
            TableConfigService.upsert_table_config(
                connection_id, spec["table_name"], data, user
            )


def seed_mappings(connection_id, user, plan, apply):
    current = {
        (m["period_offset"], m["measure_kind"], m["period_scope"]): m["column_name"]
        for m in SnapshotMappingService.list_mappings(connection_id, SALES)
    }

    desired = {
        (offset, kind, scope): column
        for offset, kind, scope, column in SALES_MAPPINGS
    }

    if current == desired:
        plan.add("unchanged", f"mappings {SALES}", f"{len(desired)} rows")
        return

    for key in sorted(set(current) | set(desired)):
        offset, kind, scope = key
        was, now = current.get(key), desired.get(key)
        label = f"  offset={offset} {kind} {scope}"

        if was == now:
            plan.add("unchanged", label, now)
        elif was is None:
            plan.add("create", label, now)
        elif now is None:
            plan.add("delete", label, f"was {was}")
        else:
            plan.add("update", label, f"{was} -> {now}")

    if apply:
        mappings = [
            {
                "period_offset": offset,
                "measure_kind": kind,
                "period_scope": scope,
                "column_name": column,
                "is_confirmed": True,
            }
            for offset, kind, scope, column in SALES_MAPPINGS
        ]

        result = SnapshotMappingService.replace_mappings(
            connection_id, SALES, mappings, user
        )

        for warning in (result or {}).get("warnings", []) or []:
            print(f"  warning: {warning}")


def seed_column_corrections(connection_id, user, plan, apply):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT dimension_id, table_name, column_name, dimension_role,
                   is_excluded, business_name, synonyms
            FROM semantic_dimensions
            WHERE connection_id = :connection_id
        """), {"connection_id": connection_id}).fetchall()

    matched = 0

    for row in rows:
        spec = COLUMN_CORRECTIONS.get((row[2] or "").upper())
        if not spec:
            continue

        matched += 1
        label = f"column {row[1]}.{row[2]}"

        if row[3] == spec["dimension_role"] and not row[4]:
            plan.add("unchanged", label, f"{row[3]}, not excluded")
            continue

        was = f"{row[3] or 'no role'}{', EXCLUDED' if row[4] else ''}"
        plan.add("update", label, f"{was} -> {spec['dimension_role']}, not excluded")

        if apply:
            ColumnConfigService.update_dimension_config(
                row[0],
                {
                    "dimension_role": spec["dimension_role"],
                    "is_excluded": False,
                    "is_confirmed": True,
                    "business_name": spec["business_name"],
                    "synonyms": spec["synonyms"],
                },
                user,
            )

    if not matched:
        # Worth saying loudly: these columns exist in the source data, so
        # finding none of them registered means auto-discovery put them
        # somewhere else - most likely semantic_metrics, which is the Step 12
        # defect - and the correction silently did nothing.
        plan.problem(
            "None of RMNAME / Cardname were found in semantic_dimensions. "
            "They may be registered as metrics instead; check before relying "
            "on grouping by party or by regional manager."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Gate 2 Step 13 - write the real semantic configuration."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the configuration. Without this the plan is printed only."
    )
    parser.add_argument(
        "--connection-id", default=None,
        help="Target connection. Defaults to the globally active one."
    )
    parser.add_argument(
        "--as-user", default="step13-seed",
        help="Employee id recorded in the audit columns."
    )
    args = parser.parse_args()

    connection_id = resolve_connection(args.connection_id)
    user = {"employee_id": args.as_user}
    plan = Plan()

    # Checked before anything is written, and a failure stops the run: a
    # configuration naming a column that does not exist saves cleanly and then
    # misbehaves at query time, which is the expensive kind of wrong.
    preflight_columns(connection_id, plan)

    if plan.problems and args.apply:
        print("\nRefusing to apply - the configuration does not match the source:")
        for problem in plan.problems:
            print(f"  - {problem}")
        return 1

    print("\n" + ("APPLYING" if args.apply else "DRY RUN - nothing will be written"))
    print("=" * 72)

    domain_ids = seed_domains(connection_id, user, plan, args.apply)
    seed_tables(connection_id, domain_ids, user, plan, args.apply)
    seed_mappings(connection_id, user, plan, args.apply)
    seed_column_corrections(connection_id, user, plan, args.apply)

    plan.render()

    print("=" * 72)
    if not plan.changes:
        print("Everything already matches. Nothing to do.")
    elif args.apply:
        print(f"Applied {len(plan.changes)} changes.")
    else:
        print(f"{len(plan.changes)} changes would be made. Re-run with --apply.")

    if plan.problems:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
