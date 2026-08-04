import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast import SQLASTParser

parser = SQLASTParser()

sql = """
SELECT TOP 5
    S.Sales,
    P.Product
FROM Sales S
JOIN Products P
ON S.ProductKey=P.ProductKey
"""

context = parser.parse(sql)

print("=" * 60)
print("ORIGINAL SQL")
print("=" * 60)
print(context.original_sql)

print()

print("=" * 60)
print("SERIALIZED SQL")
print("=" * 60)
print(context.serialized_sql)

print()

print("=" * 60)
print("AST TYPE")
print("=" * 60)
print(type(context.ast).__name__)

print()

print("=" * 60)
print("ERRORS")
print("=" * 60)
print(context.errors)