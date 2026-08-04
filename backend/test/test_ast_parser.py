import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast.parser import SQLASTParser

parser = SQLASTParser()

sql = """
SELECT TOP 10 Product,
       SUM(Sales)
FROM Sales
GROUP BY Product
"""

context = parser.parse(sql)

print("\nOriginal SQL:")
print(context.original_sql)

print("\nSerialized SQL:")
print(context.serialized_sql)

print("\nAST Type:")
print(type(context.ast).__name__)

print("\nErrors:")
print(context.errors)

print("\nWarnings:")
print(context.warnings)