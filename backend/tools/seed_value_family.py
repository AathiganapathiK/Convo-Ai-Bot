"""
Seed curated value families into semantic_value_family.

WHAT THIS DOES AND DOES NOT DO

It writes membership that a human has decided. It does NOT discover families:
every member is verified to exist in dimension_value_index before it is
written, and a member that does not exist is reported and skipped rather than
created. If a family's grouping is genuinely uncertain in the data, it does not
belong in this file until someone rules on it.

RAMRAJ is seeded here because its membership is not in doubt: Brand is a
confirmed dimension whose 43 values are brand x product-line pairs, and twelve
of them begin with RAMRAJ and nothing else does. The prefix is used HERE, once,
under human review, to propose the member list - it is not a runtime rule, and
value_family.py never infers anything.

WHAT IS DELIBERATELY NOT SEEDED

VIVEAGA (11 values) and VIVEAGHAM (9 values) coexist on ProdGrp1. They may be
one brand with a spelling inconsistency or two distinct brands. Nothing in the
data settles it, so no VIVEAG* family is written. See the report at the end of
this script's output.

    python backend/tools/seed_value_family.py                 # dry run
    python backend/tools/seed_value_family.py --apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text  # noqa: E402

from database import engine  # noqa: E402

CONNECTION_NAME = "Chatbot"

# The families a human has approved. Each names the dimension it lives on by
# physical identity, and the prefix used to PROPOSE its members - which this
# script then verifies against the index before writing anything.
APPROVED_FAMILIES = [
    {
        "table_name": "PBI_ENES_ORDER_PENDING_SUMMARY",
        "column_name": "Brand",
        "family_name": "RAMRAJ",
        "member_prefix": "RAMRAJ ",
        "rationale": (
            "Brand is a confirmed dimension holding brand x product-line "
            "pairs. RAMRAJ is one of twelve first-token brand families in it, "
            "and no other value shares the token."
        ),
    },
]

# Reported, never written. Recorded here so the open question travels with the
# code rather than living only in a chat log.
UNRESOLVED = [
    {
        "question": "Are VIVEAGA and VIVEAGHAM one brand or two?",
        "evidence": (
            "ProdGrp1 holds 11 VIVEAGA* values and 9 VIVEAGHAM* values; Brand "
            "holds 8 VIVEAGHAM* and no VIVEAGA*. Nothing in the data "
            "distinguishes a spelling inconsistency from two brands."
        ),
        "blocks": "any VIVEAG* family, and the 4 VIVEAGHAM benchmark cases",
    },
]


def resolve_connection(conn):
    row = conn.execute(text(
        "SELECT connection_id FROM database_connections WHERE connection_name = :n"
    ), {"n": CONNECTION_NAME}).fetchone()
    if not row:
        sys.exit("Could not resolve connection %r" % CONNECTION_NAME)
    return str(row[0])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="write the rows; without it this is a dry run")
    args = parser.parse_args()

    with engine.begin() as conn:
        connection_id = resolve_connection(conn)
        print("connection %s -> %s" % (CONNECTION_NAME, connection_id))
        print()

        for spec in APPROVED_FAMILIES:
            dim = conn.execute(text("""
                SELECT dimension_id, business_name
                FROM semantic_dimensions
                WHERE connection_id = :c AND table_name = :t AND column_name = :col
                  AND is_active = 1
            """), {"c": connection_id, "t": spec["table_name"],
                   "col": spec["column_name"]}).fetchone()

            if not dim:
                print("SKIP %s: no active dimension %s.%s"
                      % (spec["family_name"], spec["table_name"], spec["column_name"]))
                continue

            dimension_id, business_name = str(dim[0]), dim[1]

            # Members are proposed by prefix and then VERIFIED against the
            # index. Only values that actually exist are written.
            indexed = [r[0] for r in conn.execute(text("""
                SELECT value FROM dimension_value_index
                WHERE connection_id = :c AND semantic_dimension_id = :d
                ORDER BY value
            """), {"c": connection_id, "d": dimension_id})]

            members = [v for v in indexed
                       if v.upper().startswith(spec["member_prefix"].upper())]

            print("family %s on %s (%s.%s)"
                  % (spec["family_name"], business_name,
                     spec["table_name"], spec["column_name"]))
            print("  rationale: %s" % spec["rationale"])
            print("  %d of %d indexed values matched:" % (len(members), len(indexed)))
            for m in members:
                print("     %s" % m)

            if len(members) < 2:
                print("  SKIP: fewer than two members is not a family")
                print()
                continue

            if not args.apply:
                print("  dry run - nothing written")
                print()
                continue

            written = 0
            for member in members:
                exists = conn.execute(text("""
                    SELECT 1 FROM semantic_value_family
                    WHERE connection_id = :c AND dimension_id = :d
                      AND family_name = :f AND member_value = :m
                """), {"c": connection_id, "d": dimension_id,
                       "f": spec["family_name"], "m": member}).fetchone()
                if exists:
                    continue
                conn.execute(text("""
                    INSERT INTO semantic_value_family
                        (connection_id, dimension_id, family_name,
                         member_value, is_confirmed, created_by)
                    VALUES (:c, :d, :f, :m, 1, 'seed_value_family')
                """), {"c": connection_id, "d": dimension_id,
                       "f": spec["family_name"], "m": member})
                written += 1
            print("  wrote %d new member rows (confirmed)" % written)
            print()

    print("=" * 70)
    print("OPEN BUSINESS DECISIONS - not seeded, deliberately")
    print("=" * 70)
    for item in UNRESOLVED:
        print("  %s" % item["question"])
        print("    evidence: %s" % item["evidence"])
        print("    blocks  : %s" % item["blocks"])


if __name__ == "__main__":
    main()
