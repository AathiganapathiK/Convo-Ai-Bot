import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast import (
    SQLASTParser,
    SQLASTMetadataExtractor,
    SQLASTSchemaValidator,
)

from ai.schema_loader import get_schema_metadata

parser = SQLASTParser()

extractor = SQLASTMetadataExtractor()

validator = SQLASTSchemaValidator()

sql = """
SELECT
    S.Sales,
    P.Product
FROM Sales S
JOIN Products P
ON S.ProductKey=P.ProductKey
"""

context = parser.parse(sql)

if context.ast is None:
    print("Failed to build SQL AST.")
    sys.exit(1)

metadata = extractor.extract(context.ast)

schema = validator.validate(
    metadata,
    get_schema_metadata()
)

print("="*60)
print("PASSED")
print("="*60)

print(schema.passed)

print()

print("="*60)
print("ERRORS")
print("="*60)

print(schema.errors)

print()

print("="*60)
print("WARNINGS")
print("="*60)

print(schema.warnings)