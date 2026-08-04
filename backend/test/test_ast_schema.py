import sys
import os
import unittest

# Adjust Python path to resolve the 'ai' package from the backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast.parser import SQLASTParser
from ai.ast.metadata import SQLASTMetadataExtractor
from ai.ast.schema import SQLASTSchemaValidator


class TestASTSchemaValidator(unittest.TestCase):
    def setUp(self):
        self.parser = SQLASTParser()
        self.extractor = SQLASTMetadataExtractor()
        self.validator = SQLASTSchemaValidator()
        self.schema_metadata = {
            "dbo.Sales": {
                "columns": {
                    "salesamount",
                    "orderdate",
                    "productkey",
                    "regionkey",
                    "sales",
                }
            },
            "dbo.Products": {
                "columns": {
                    "productkey",
                    "productname",
                    "price",
                    "product",
                }
            },
            "dbo.Region": {
                "columns": {
                    "regionkey",
                    "regionname",
                    "region",
                }
            }
        }

    def validate_sql(self, sql: str):
        context = self.parser.parse(sql)
        self.assertIsNotNone(context.ast, f"Failed to parse query: {sql}")
        metadata = self.extractor.extract(context.ast)
        return self.validator.validate(metadata, self.schema_metadata)

    def assert_validation_passes(self, sql: str):
        res = self.validate_sql(sql)
        self.assertTrue(
            res.passed,
            f"Query expected to pass schema validation but failed.\nSQL: {sql}\nErrors: {res.errors}"
        )

    def assert_validation_fails(self, sql: str, expected_errors: list[str] = None):
        res = self.validate_sql(sql)
        self.assertFalse(
            res.passed,
            f"Query expected to fail schema validation but passed.\nSQL: {sql}"
        )
        if expected_errors:
            for expected in expected_errors:
                matched = any(expected.lower() in err.lower() for err in res.errors)
                self.assertTrue(
                    matched,
                    f"Expected error matching '{expected}' not found in: {res.errors}"
                )

    def test_valid_simple_query(self):
        sql = "SELECT Sales, ProductKey FROM Sales"
        self.assert_validation_passes(sql)

    def test_invalid_table(self):
        sql = "SELECT * FROM NonExistentTable"
        self.assert_validation_fails(sql, ["table 'NonExistentTable' does not exist"])

    def test_invalid_selected_column(self):
        sql = "SELECT InvalidColumn FROM Sales"
        self.assert_validation_fails(sql, ["column 'InvalidColumn' does not exist on table 'dbo.Sales'"])

    def test_valid_aliases(self):
        sql = "SELECT S.Sales, P.Product FROM Sales S JOIN Products P ON S.ProductKey = P.ProductKey"
        self.assert_validation_passes(sql)

    def test_invalid_alias_reference(self):
        # Column referenced with an alias that does not exist
        sql = "SELECT X.Sales FROM Sales S"
        self.assert_validation_fails(sql, ["alias or table 'X' used in column reference 'X.Sales' does not exist in FROM/JOIN"])

    def test_invalid_join_column(self):
        sql = "SELECT S.Sales FROM Sales S JOIN Products P ON S.InvalidKey = P.ProductKey"
        self.assert_validation_fails(sql, ["column 'InvalidKey' does not exist on table 'dbo.Sales' in JOIN condition"])

    def test_invalid_where_column(self):
        sql = "SELECT Sales FROM Sales WHERE InvalidColumn = 1"
        self.assert_validation_fails(sql, ["column 'InvalidColumn' does not exist on table 'dbo.Sales' in WHERE clause"])

    def test_invalid_group_by_column(self):
        sql = "SELECT Sales FROM Sales GROUP BY InvalidColumn"
        self.assert_validation_fails(sql, ["column 'InvalidColumn' does not exist on table 'dbo.Sales' in GROUP BY clause"])

    def test_invalid_having_column(self):
        sql = "SELECT SUM(Sales) FROM Sales GROUP BY ProductKey HAVING SUM(InvalidColumn) > 10"
        self.assert_validation_fails(sql, ["column 'InvalidColumn' does not exist on table 'dbo.Sales' in HAVING clause"])

    def test_invalid_order_by_column(self):
        sql = "SELECT Sales FROM Sales ORDER BY InvalidColumn"
        self.assert_validation_fails(sql, ["column 'InvalidColumn' does not exist on table 'dbo.Sales' in ORDER BY clause"])

    def test_cte_validation_bypass(self):
        sql = """
        WITH SalesCTE AS (
            SELECT Sales, ProductKey FROM Sales
        )
        SELECT CTECol FROM SalesCTE
        """
        # Since SalesCTE is a CTE, CTECol or any columns on SalesCTE are assumed to be valid and not checked against the physical schema
        self.assert_validation_passes(sql)

    def test_ambiguous_column(self):
        sql = """
        SELECT ProductKey
        FROM Sales S
        JOIN Products P ON S.ProductKey = P.ProductKey
        """
        self.assert_validation_fails(
            sql,
            [
                "Ambiguous column 'ProductKey'",
                "Found in:",
                "- dbo.Sales",
                "- dbo.Products",
                "Qualify the column using a table alias."
            ]
        )


if __name__ == "__main__":
    unittest.main()
