import sys
import os
import unittest

# Adjust Python path to resolve the 'ai' package from the backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast.parser import SQLASTParser
from ai.ast.metadata import SQLASTMetadataExtractor
from ai.ast.models import TableInfo, ColumnInfo, JoinInfo, AggregateInfo, OrderByInfo, PredicateInfo, WindowFunctionInfo


class TestASTMetadataExtractor(unittest.TestCase):
    """
    Test suite for SQL AST Metadata Extraction.
    """

    def setUp(self):
        self.parser = SQLASTParser()
        self.extractor = SQLASTMetadataExtractor()

    def get_metadata(self, sql: str):
        context = self.parser.parse(sql)
        self.assertIsNotNone(context.ast, f"Failed to parse query: {sql}")
        return self.extractor.extract(context.ast)

    def test_extract_tables(self):
        sql = """
        SELECT *
        FROM Sales S
        JOIN Products P ON S.ProductKey = P.ProductKey
        LEFT JOIN Region R ON S.RegionKey = R.RegionKey
        """
        metadata = self.get_metadata(sql)
        
        expected_tables = [
            TableInfo(name="Sales", alias="S"),
            TableInfo(name="Products", alias="P"),
            TableInfo(name="Region", alias="R")
        ]
        self.assertEqual(metadata.tables, expected_tables)

    def test_extract_columns(self):
        sql = "SELECT Product, Sales, Price AS UnitPrice FROM Sales"
        metadata = self.get_metadata(sql)

        expected_columns = [
            ColumnInfo(name="Product", table=None, alias=None),
            ColumnInfo(name="Sales", table=None, alias=None),
            ColumnInfo(name="Price", table=None, alias="UnitPrice")
        ]
        self.assertEqual(metadata.selected_columns, expected_columns)

    def test_extract_joins(self):
        sql = """
        SELECT *
        FROM Sales S
        JOIN Products P ON S.ProductKey = P.ProductKey
        LEFT JOIN Region R ON S.RegionKey = R.RegionKey
        RIGHT OUTER JOIN Salesperson SP ON S.EmployeeKey = SP.EmployeeKey
        CROSS JOIN Targets T
        """
        metadata = self.get_metadata(sql)

        expected_joins = [
            JoinInfo(join_type="INNER", table="Products", alias="P", condition="S.ProductKey = P.ProductKey"),
            JoinInfo(join_type="LEFT", table="Region", alias="R", condition="S.RegionKey = R.RegionKey"),
            JoinInfo(join_type="RIGHT OUTER", table="Salesperson", alias="SP", condition="S.EmployeeKey = SP.EmployeeKey"),
            JoinInfo(join_type="CROSS", table="Targets", alias="T", condition="")
        ]
        self.assertEqual(metadata.joins, expected_joins)

    def test_extract_aggregates(self):
        sql = """
        SELECT SUM(Sales), AVG(Price), COUNT(Product), MIN(Cost), MAX(Quantity)
        FROM Sales
        """
        metadata = self.get_metadata(sql)

        expected_aggregates = [
            AggregateInfo(function="SUM", column="Sales"),
            AggregateInfo(function="AVG", column="Price"),
            AggregateInfo(function="COUNT", column="Product"),
            AggregateInfo(function="MIN", column="Cost"),
            AggregateInfo(function="MAX", column="Quantity")
        ]
        self.assertEqual(metadata.aggregates, expected_aggregates)

    def test_extract_group_by(self):
        sql = "SELECT Product, SUM(Sales) FROM Sales GROUP BY Product, Region"
        metadata = self.get_metadata(sql)

        self.assertEqual(metadata.group_by, ["Product", "Region"])

    def test_extract_order_by(self):
        sql = "SELECT * FROM Sales ORDER BY Sales DESC, Product ASC"
        metadata = self.get_metadata(sql)

        expected_order_by = [
            OrderByInfo(column="Sales", direction="DESC"),
            OrderByInfo(column="Product", direction="ASC")
        ]
        self.assertEqual(metadata.order_by, expected_order_by)

    def test_extract_where(self):
        sql = "SELECT * FROM Sales WHERE Sales > 1000 AND Region = 'North'"
        metadata = self.get_metadata(sql)

        expected_where = [
            PredicateInfo(expression="Sales > 1000"),
            PredicateInfo(expression="Region = 'North'")
        ]
        self.assertEqual(metadata.where, expected_where)

    def test_extract_having(self):
        sql = "SELECT Product, SUM(Sales) FROM Sales GROUP BY Product HAVING SUM(Sales) > 1000 AND SUM(Sales) < 5000"
        metadata = self.get_metadata(sql)

        expected_having = [
            PredicateInfo(expression="SUM(Sales) > 1000"),
            PredicateInfo(expression="SUM(Sales) < 5000")
        ]
        self.assertEqual(metadata.having, expected_having)

    def test_extract_limit_and_top(self):
        # Test LIMIT syntax
        sql_limit = "SELECT * FROM Sales LIMIT 15"
        metadata_limit = self.get_metadata(sql_limit)
        self.assertEqual(metadata_limit.limit, 15)

        # Test TOP syntax (TSQL dialect is the default in parser)
        sql_top = "SELECT TOP 10 * FROM Sales"
        metadata_top = self.get_metadata(sql_top)
        self.assertEqual(metadata_top.limit, 10)

    def test_extract_window_functions(self):
        sql = """
        SELECT
            ROW_NUMBER() OVER(PARTITION BY Region ORDER BY Sales DESC) as RowNum,
            RANK() OVER(ORDER BY Sales DESC) as Rnk,
            DENSE_RANK() OVER(ORDER BY Sales DESC) as DenseRnk
        FROM Sales
        """
        metadata = self.get_metadata(sql)

        expected_windows = [
            WindowFunctionInfo(function="ROW_NUMBER"),
            WindowFunctionInfo(function="RANK"),
            WindowFunctionInfo(function="DENSE_RANK")
        ]
        self.assertEqual(metadata.window_functions, expected_windows)

    def test_extract_ctes(self):
        sql = """
        WITH MonthlySales AS (
            SELECT Product, SUM(Sales) AS TotalSales
            FROM Sales
            GROUP BY Product
        )
        SELECT * FROM MonthlySales
        """
        metadata = self.get_metadata(sql)

        # CTE should be extracted
        self.assertEqual(metadata.ctes, ["MonthlySales"])

        # Tables list should NOT contain the CTE name
        expected_tables = [TableInfo(name="Sales", alias=None)]
        self.assertEqual(metadata.tables, expected_tables)

    def test_extract_subqueries(self):
        sql = """
        SELECT *
        FROM (SELECT * FROM Sales) AS S
        WHERE Sales > (SELECT AVG(Sales) FROM Sales)
          AND EXISTS (SELECT 1 FROM Products P WHERE P.ProductKey = S.ProductKey)
        """
        metadata = self.get_metadata(sql)

        # 1 from clause subquery, 1 scalar subquery, 1 exists subquery = 3 subqueries
        self.assertEqual(metadata.subquery_count, 3)

    def test_metadata_deduplication(self):
        # Query with duplicate columns, tables, joins, aggregates, group bys, order bys, and predicates
        sql = """
        SELECT Product, Product, Sales, SUM(Sales), SUM(Sales)
        FROM Sales S
        JOIN Products P ON S.ProductKey = P.ProductKey
        JOIN Products P ON S.ProductKey = P.ProductKey
        WHERE Sales > 1000 AND Sales > 1000 AND Region = 'North'
        GROUP BY Product, Product
        ORDER BY Sales DESC, Sales DESC
        """
        metadata = self.get_metadata(sql)

        # Tables: Sales, Products (both only once)
        expected_tables = [
            TableInfo(name="Sales", alias="S"),
            TableInfo(name="Products", alias="P")
        ]
        self.assertEqual(metadata.tables, expected_tables)

        # Selected Columns: Product, Sales
        expected_columns = [
            ColumnInfo(name="Product", table=None, alias=None),
            ColumnInfo(name="Sales", table=None, alias=None)
        ]
        self.assertEqual(metadata.selected_columns, expected_columns)

        # Joins: Only 1 unique join
        expected_joins = [
            JoinInfo(join_type="INNER", table="Products", alias="P", condition="S.ProductKey = P.ProductKey")
        ]
        self.assertEqual(metadata.joins, expected_joins)

        # Aggregates: Only 1 unique SUM(Sales)
        expected_aggregates = [
            AggregateInfo(function="SUM", column="Sales")
        ]
        self.assertEqual(metadata.aggregates, expected_aggregates)

        # Group By: Only 1 unique Product
        self.assertEqual(metadata.group_by, ["Product"])

        # Order By: Only 1 unique Sales DESC
        expected_order_by = [
            OrderByInfo(column="Sales", direction="DESC")
        ]
        self.assertEqual(metadata.order_by, expected_order_by)

        # Where: Only unique predicates: Sales > 1000, Region = 'North'
        expected_where = [
            PredicateInfo(expression="Sales > 1000"),
            PredicateInfo(expression="Region = 'North'")
        ]
        self.assertEqual(metadata.where, expected_where)


if __name__ == "__main__":
    unittest.main()
