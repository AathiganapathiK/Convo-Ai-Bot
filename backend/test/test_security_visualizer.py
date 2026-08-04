import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast import SQLASTParser
from ai.ast import SQLASTSecurityValidator

parser = SQLASTParser()
security = SQLASTSecurityValidator()

queries = [

    "SELECT * FROM Sales",

    "DROP TABLE Sales",

    "DELETE FROM Sales",

    "SELECT * FROM Sales; DROP TABLE Sales",

]

for sql in queries:

    print("="*70)
    print(sql)

    context = parser.parse(sql)

    if context.ast is None:
        print(context.errors)
        continue

    result = security.validate_ast(context.ast)

    print(result)