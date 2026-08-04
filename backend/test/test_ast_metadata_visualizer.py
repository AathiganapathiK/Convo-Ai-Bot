import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast import SQLASTParser
from ai.ast.metadata import SQLASTMetadataExtractor

parser = SQLASTParser(dialect="tsql")
extractor = SQLASTMetadataExtractor()

sql = """
WITH SalesCTE AS
(
    SELECT
        S.EmployeeKey,
        SUM(S.Sales) AS TotalSales
    FROM Sales S
    WHERE S.Sales > 1000
    GROUP BY S.EmployeeKey
)
SELECT TOP 3
    SP.Salesperson,
    C.TotalSales,
    ROW_NUMBER() OVER (ORDER BY C.TotalSales DESC) AS Rank
FROM SalesCTE C
INNER JOIN Salesperson SP
ON C.EmployeeKey = SP.EmployeeKey
ORDER BY C.TotalSales DESC
"""

context = parser.parse(sql)
if context.ast is None:
    raise ValueError("AST is missing.")
metadata = extractor.extract(context.ast)

print("\n" + "=" * 70)
print("SQL METADATA")
print("=" * 70)

print("\nTables")
print("-" * 30)
for t in metadata.tables:
    print(f"{t.name}  Alias={t.alias}")

print("\nColumns")
print("-" * 30)
for c in metadata.selected_columns:
    print(f"{c.table}.{c.name}  Alias={c.alias}")

print("\nJoins")
print("-" * 30)
for j in metadata.joins:
    print(
        f"{j.join_type} | "
        f"{j.table} | "
        f"Alias={j.alias} | "
        f"ON {j.condition}"
    )

print("\nAggregates")
print("-" * 30)
for a in metadata.aggregates:
    print(f"{a.function}({a.column})")

print("\nGroup By")
print("-" * 30)
for g in metadata.group_by:
    print(g)

print("\nOrder By")
print("-" * 30)
for o in metadata.order_by:
    print(f"{o.column} {o.direction}")

print("\nWhere")
print("-" * 30)
for w in metadata.where:
    print(w.expression)

print("\nHaving")
print("-" * 30)
for h in metadata.having:
    print(h.expression)

print("\nCTEs")
print("-" * 30)
for c in metadata.ctes:
    print(c)

print("\nWindow Functions")
print("-" * 30)
for w in metadata.window_functions:
    print(w.function)

print("\nSubquery Count")
print("-" * 30)
print(metadata.subquery_count)

print("\nLimit")
print("-" * 30)
print(metadata.limit)

print("\n" + "=" * 70)