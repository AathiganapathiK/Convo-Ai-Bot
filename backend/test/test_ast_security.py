import sys
import os
import unittest

# Adjust Python path to resolve the 'ai' package from the backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast.parser import SQLASTParser
from ai.ast.security import SQLASTSecurityValidator


class TestASTSecurity(unittest.TestCase):
    """
    Test suite for AST-based SQL Security validation.
    """

    def setUp(self):
        self.parser = SQLASTParser()
        self.validator = SQLASTSecurityValidator()

    def assert_sql_passes(self, sql: str):
        context = self.parser.parse(sql)
        self.assertIsNotNone(context.ast, f"Failed to parse query: {sql}")
        res = self.validator.validate_ast(context.ast)
        self.assertTrue(
            res.passed,
            f"Query was expected to PASS but FAILED.\nSQL: {sql}\nErrors: {res.errors}"
        )

    def assert_sql_fails(self, sql: str, expected_error_substrings: list = None):
        context = self.parser.parse(sql)
        self.assertIsNotNone(context.ast, f"Failed to parse query: {sql}")
        res = self.validator.validate_ast(context.ast)
        self.assertFalse(
            res.passed,
            f"Query was expected to FAIL but PASSED.\nSQL: {sql}"
        )
        
        if expected_error_substrings:
            for substring in expected_error_substrings:
                matched = any(substring.lower() in err.lower() for err in res.errors)
                self.assertTrue(
                    matched,
                    f"Expected error message containing '{substring}' not found in: {res.errors}"
                )

    # -------------------------------------------------------------------------
    # Should Pass Cases
    # -------------------------------------------------------------------------

    def test_simple_select(self):
        sql = "SELECT Product, Sales FROM Sales"
        self.assert_sql_passes(sql)

    def test_aggregate(self):
        sql = """
        SELECT Product, SUM(Sales) AS TotalSales
        FROM Sales
        GROUP BY Product
        """
        self.assert_sql_passes(sql)

    def test_join(self):
        sql = """
        SELECT S.Sales, P.Product
        FROM Sales S
        JOIN Products P ON S.ProductKey = P.ProductKey
        """
        self.assert_sql_passes(sql)

    def test_union(self):
        sql = """
        SELECT Product FROM Sales
        UNION
        SELECT Product FROM ArchiveSales
        """
        self.assert_sql_passes(sql)

    def test_cte(self):
        sql = """
        WITH SalesCTE AS (
            SELECT Product, Sales FROM Sales
        )
        SELECT * FROM SalesCTE
        """
        self.assert_sql_passes(sql)

    def test_exists(self):
        sql = """
        SELECT * FROM Sales S
        WHERE EXISTS (
            SELECT 1 FROM Products P WHERE P.ProductKey = S.ProductKey
        )
        """
        self.assert_sql_passes(sql)

    def test_window_function(self):
        sql = """
        SELECT Product,
               ROW_NUMBER() OVER (PARTITION BY Category ORDER BY Sales DESC) as Rank
        FROM Sales
        """
        self.assert_sql_passes(sql)

    # -------------------------------------------------------------------------
    # Should Fail Cases
    # -------------------------------------------------------------------------

    def test_drop_table(self):
        sql = "DROP TABLE Sales"
        self.assert_sql_fails(sql, ["DROP statements are not allowed."])

    def test_delete(self):
        sql = "DELETE FROM Sales"
        self.assert_sql_fails(sql, ["DELETE statements are not allowed."])

    def test_update(self):
        sql = "UPDATE Sales SET Sales = 1000 WHERE ProductKey = 1"
        self.assert_sql_fails(sql, ["UPDATE statements are not allowed."])

    def test_insert(self):
        sql = "INSERT INTO Sales (ProductKey, Sales) VALUES (1, 100)"
        self.assert_sql_fails(sql, ["INSERT statements are not allowed."])

    def test_alter(self):
        sql = "ALTER TABLE Sales ADD NewColumn INT"
        self.assert_sql_fails(sql, ["ALTER statements are not allowed."])

    def test_create(self):
        sql = "CREATE TABLE NewTable (ID INT)"
        self.assert_sql_fails(sql, ["CREATE statements are not allowed."])

    def test_multiple_statements(self):
        sql = "SELECT * FROM Sales; DROP TABLE Sales;"
        self.assert_sql_fails(sql, ["Multiple SQL statements detected.", "DROP statements are not allowed."])

    def test_truncate(self):
        sql = "TRUNCATE TABLE Sales"
        self.assert_sql_fails(sql, ["TRUNCATE statements are not allowed."])

    def test_merge(self):
        sql = """
        MERGE INTO TargetTable AS T
        USING SourceTable AS S
        ON T.ID = S.ID
        WHEN MATCHED THEN UPDATE SET T.Val = S.Val;
        """
        self.assert_sql_fails(sql, ["MERGE statements are not allowed."])


if __name__ == "__main__":
    unittest.main()
