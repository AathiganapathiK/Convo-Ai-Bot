"""
Tests for parse-failure handling in ValidationPipeline.

WHY THIS EXISTS
    SQLASTParser signals a parse failure by RAISING ASTParserError rather than
    returning a context with errors populated. ValidationPipeline.validate()
    called it unguarded, so unparseable SQL escaped as an exception.

    ASTParserError is not an EnterpriseException, so it fell past the handler
    in app.py that turns validation problems into an HTTP 400 and landed in the
    generic handler, producing an HTTP 500. The query was also never recorded
    as SQL_VALIDATION_FAILED, so unparseable SQL was invisible in query history.

    Malformed SQL never reached the database either before or after this change -
    the pipeline failed closed both ways. What changed is that it now fails on
    the ordinary validation path instead of as an unhandled exception.

    These tests use a synthetic schema and touch no database.
"""

import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast.exceptions import ASTParserError
from ai.ast.metadata import SQLASTMetadataExtractor
from ai.ast.parser import SQLASTParser
from ai.ast.schema import SQLASTSchemaValidator
from ai.ast.security import SQLASTSecurityValidator
from ai.validation_pipeline import ValidationPipeline, ValidationPipelineResult


SCHEMA = {
    "dbo.Sales": {
        "columns": {"cy", "py", "state1", "productkey"}
    },
    "dbo.Products": {
        "columns": {"productkey", "productname"}
    },
}

UNPARSEABLE = [
    "SELECT FROM WHERE",
    "SELECT * FROM",
    "SELECT (((",
    "SELECT 1 +",
]


class TestParseFailureHandling(unittest.TestCase):

    def setUp(self):
        self.pipeline = ValidationPipeline(
            SQLASTParser(),
            SQLASTSecurityValidator(),
            SQLASTMetadataExtractor(),
            SQLASTSchemaValidator(),
        )

    def test_parser_still_raises_on_its_own(self):
        """
        The parser's own behaviour is deliberately unchanged - it still raises.
        Only the pipeline's handling of that was fixed.
        """

        with self.assertRaises(ASTParserError):
            SQLASTParser().parse("SELECT FROM WHERE")

    def test_exception_does_not_escape_validate(self):
        """The point of the fix: validate() returns, it does not raise."""

        for sql in UNPARSEABLE:
            with self.subTest(sql=sql):
                try:
                    result = self.pipeline.validate(sql, SCHEMA)
                except Exception as ex:
                    self.fail(
                        f"validate() raised {type(ex).__name__} for {sql!r}. "
                        "Unparseable SQL must come back as a failed result, "
                        "not as an exception - an exception becomes an HTTP "
                        "500 instead of a validation error."
                    )

                self.assertIsInstance(result, ValidationPipelineResult)

    def test_malformed_sql_returns_passed_false(self):
        for sql in UNPARSEABLE:
            with self.subTest(sql=sql):
                result = self.pipeline.validate(sql, SCHEMA)

                self.assertFalse(result.passed)

    def test_result_carries_a_clear_error(self):
        result = self.pipeline.validate("SELECT FROM WHERE", SCHEMA)

        self.assertIsNotNone(result.error)
        self.assertIn("could not be parsed", result.error)
        self.assertTrue(len(result.error) > 20)

    def test_context_records_the_parse_error(self):
        result = self.pipeline.validate("SELECT FROM WHERE", SCHEMA)

        self.assertIsNotNone(result.context)
        self.assertEqual(result.context.original_sql, "SELECT FROM WHERE")
        self.assertTrue(result.context.errors)

    def test_parse_failure_leaves_schema_result_unset(self):
        """
        validate_sql_query() only calls RepairEngine when schema_result is
        present. A parse failure must leave it None so the caller returns the
        error directly instead of trying to repair SQL that has no AST.
        """

        result = self.pipeline.validate("SELECT FROM WHERE", SCHEMA)

        self.assertIsNone(result.schema_result)
        self.assertIsNone(result.metadata)


class TestExistingBehaviourUnchanged(unittest.TestCase):
    """Regression guard - the fix must not alter anything else."""

    def setUp(self):
        self.pipeline = ValidationPipeline(
            SQLASTParser(),
            SQLASTSecurityValidator(),
            SQLASTMetadataExtractor(),
            SQLASTSchemaValidator(),
        )

    def test_valid_sql_still_passes(self):
        result = self.pipeline.validate(
            "SELECT SUM(CY) FROM Sales WHERE State1 = 'TN'",
            SCHEMA,
        )

        self.assertTrue(result.passed, result.error)
        self.assertIsNotNone(result.metadata)
        self.assertIsNotNone(result.schema_result)

    def test_valid_join_still_passes(self):
        result = self.pipeline.validate(
            "SELECT S.ProductKey FROM Sales S "
            "JOIN Products P ON S.ProductKey = P.ProductKey",
            SCHEMA,
        )

        self.assertTrue(result.passed, result.error)

    def test_unknown_column_still_fails_schema_validation(self):
        result = self.pipeline.validate(
            "SELECT SUM(customer_revenue) FROM Sales",
            SCHEMA,
        )

        self.assertFalse(result.passed)
        self.assertIsNotNone(result.schema_result)
        self.assertEqual(
            result.schema_result.errors[0].code.value,
            "COLUMN_NOT_FOUND",
        )

    def test_unknown_table_still_fails_schema_validation(self):
        result = self.pipeline.validate("SELECT CY FROM Ghost", SCHEMA)

        self.assertFalse(result.passed)
        self.assertEqual(
            result.schema_result.errors[0].code.value,
            "TABLE_NOT_FOUND",
        )

    def test_dangerous_statement_still_fails_security(self):
        result = self.pipeline.validate("DELETE FROM Sales", SCHEMA)

        self.assertFalse(result.passed)
        self.assertIsNotNone(result.security_result)
        self.assertFalse(result.security_result.passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
