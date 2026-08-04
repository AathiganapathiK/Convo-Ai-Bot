import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast import (
    SQLASTParser,
    SQLASTSecurityValidator,
    SQLASTMetadataExtractor,
    SQLASTSchemaValidator,
)

from ai.schema_loader import get_schema_metadata

parser = SQLASTParser()

security = SQLASTSecurityValidator()

extractor = SQLASTMetadataExtractor()

schema_validator = SQLASTSchemaValidator()

queries = [

    "SELECT Sales FROM Sales",

    "SELECT InvalidColumn FROM Sales",

    "DROP TABLE Sales",

    "SELECT ProductKey FROM Sales S JOIN Products P ON S.ProductKey=P.ProductKey",

    "SELECT S.ProductKey FROM Sales S JOIN Products P ON S.ProductKey=P.ProductKey",

]

schema_metadata = get_schema_metadata()

for sql in queries:

    print("\n" + "="*80)

    print(sql)

    context = parser.parse(sql)

    if context.errors:
        print("Parser")
        print(context.errors)
        continue
    if context.ast is None:
        raise ValueError("AST is missing.")
    security_result = security.validate_ast(context.ast)

    if not security_result.passed:
        print("Security")
        print(security_result.errors)
        continue

    metadata = extractor.extract(context.ast)

    schema_result = schema_validator.validate(
        metadata,
        schema_metadata
    )

    if not schema_result.passed:
        print("Schema")
        print(schema_result.errors)
        continue

    print("PASS")