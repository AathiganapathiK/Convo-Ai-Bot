"""
Gate 2 Step 12 - report columns that appear to hold the same values.

Reports only. It changes nothing, and that is the point: which of State1,
State2, State3 and StateCode the business actually means is not a decision a
scan can make, and auto-excluding the "duplicates" would be choosing a winner
by row order. The output is a list for a person to act on through the existing
review screens.

    python tools/report_duplicate_columns.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.config  # noqa: F401,E402
from database import engine  # noqa: E402
from services.connection_manager import ConnectionManager  # noqa: E402
from services.connection_service import ConnectionService  # noqa: E402
from semantic.discovery_policy import find_equivalent_columns  # noqa: E402


def main():
    connection = ConnectionService.get_active_connection_global()
    if not connection:
        sys.exit("No active database connection.")

    print("Connection: %s (%s)\n" % (
        connection.get("connection_name"), connection["connection_id"]
    ))

    source = ConnectionManager.source(connection=connection)

    with engine.connect() as platform_conn:
        findings = find_equivalent_columns(
            connection["connection_id"], platform_conn, source
        )

    if not findings:
        print("No equivalent columns found.")
        return 0

    print("%d pair(s) worth a decision. Nothing has been changed.\n" % len(findings))

    current_table = None
    for f in findings:
        if f["table_name"] != current_table:
            current_table = f["table_name"]
            print("\n%s" % current_table)
            print("-" * len(current_table))

        left, right = f["columns"]
        print("  %-14s vs %-14s  %-10s  %d and %d distinct, %d shared (overlap %.0f%%)"
              % (left, right, f["relation"], f["distinct"][0], f["distinct"][1],
                 f["overlap"], f["jaccard"] * 100))
        print("     %s" % f["proposal"])

    print(
        "\nTo act on any of these, exclude the column you do not want from the "
        "Semantic Control Center. Nothing here writes to the database."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
