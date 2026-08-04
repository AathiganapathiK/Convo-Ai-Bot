from sqlglot import parse_one
from sqlglot.errors import ParseError

from .exceptions import ASTParserError
from .models import ValidationContext


class SQLASTParser:
    """
    Enterprise wrapper around sqlglot.

    Responsibilities:
    - Parse SQL
    - Normalize SQL
    - Populate ValidationContext

    Does NOT:
    - Validate security
    - Validate schema
    - Execute SQL
    """

    def __init__(self, dialect: str = "tsql"):
        self.dialect = dialect

    def parse(self, sql: str) -> ValidationContext:
        """
        Parse SQL and return a ValidationContext.
        """

        context = ValidationContext(original_sql=sql)

        try:
            ast = parse_one(sql, dialect=self.dialect)

            context.ast = ast
            context.serialized_sql = ast.sql(dialect=self.dialect)

            return context

        except ParseError as ex:
            raise ASTParserError(str(ex)) from ex