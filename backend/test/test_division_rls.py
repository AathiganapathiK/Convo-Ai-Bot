import sys
import os
import unittest
from unittest.mock import patch

# Adjust path to resolve packages from backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from security.division_rls_engine import DivisionRLSEngine

class TestDivisionRLS(unittest.TestCase):
    def setUp(self):
        # Sample division tables config for mock
        self.division_tables = {
            "sales": "division",
            "orders": "division_code",
            "customers": "division"
        }

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_unrestricted_user_bypass(self, mock_get_tables):
        # If division_code is None or empty, RLS must bypass completely and not even look up tables.
        sql = "SELECT * FROM Sales"
        res = DivisionRLSEngine.apply_division_rls(sql, division_code=None, connection_id="conn_1")
        self.assertEqual(res, sql)
        mock_get_tables.assert_not_called()

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_non_scoped_datasource_bypass(self, mock_get_tables):
        # If the datasource does not have any division tables, query must be unmodified.
        mock_get_tables.return_value = {}
        sql = "SELECT * FROM Sales"
        res = DivisionRLSEngine.apply_division_rls(sql, division_code="VCC", connection_id="conn_1")
        self.assertEqual(res, sql)
        mock_get_tables.assert_called_once_with("conn_1")

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_simple_select_filter(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT * FROM Sales"
        expected = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_existing_where_clause(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT * FROM Sales WHERE SalesAmount > 100"
        expected = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales WHERE SalesAmount > 100"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_group_by_order_by(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT Category, SUM(SalesAmount) FROM Sales GROUP BY Category ORDER BY Category"
        expected = "SELECT Category, SUM(SalesAmount) FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales GROUP BY Category ORDER BY Category"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_join_query_with_alias(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT * FROM Sales s JOIN Products p ON s.ProductKey = p.ProductKey WHERE p.Category = 'Bikes'"
        expected = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s JOIN Products AS p ON s.ProductKey = p.ProductKey WHERE p.Category = 'Bikes'"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_nested_subquery(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT * FROM (SELECT * FROM Sales WHERE Year = 2026) s JOIN Regions r ON s.RegionKey = r.RegionKey"
        expected = "SELECT * FROM (SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales WHERE Year = 2026) AS s JOIN Regions AS r ON s.RegionKey = r.RegionKey"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_cte_query(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "WITH SalesCTE AS (SELECT * FROM Sales) SELECT * FROM SalesCTE"
        expected = "WITH SalesCTE AS (SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales) SELECT * FROM SalesCTE"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_union_and_union_all(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        
        # Test UNION
        sql1 = "SELECT * FROM Sales UNION SELECT * FROM Orders"
        expected1 = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales UNION SELECT * FROM (SELECT * FROM Orders WHERE Orders.division_code = 'VCC') AS Orders"
        res1 = DivisionRLSEngine.apply_division_rls(sql1, "VCC", "conn_1")
        self.assertEqual(res1.replace(" ", "").upper(), expected1.replace(" ", "").upper())

        # Test UNION ALL
        sql2 = "SELECT * FROM Sales UNION ALL SELECT * FROM Orders"
        expected2 = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales UNION ALL SELECT * FROM (SELECT * FROM Orders WHERE Orders.division_code = 'VCC') AS Orders"
        res2 = DivisionRLSEngine.apply_division_rls(sql2, "VCC", "conn_1")
        self.assertEqual(res2.replace(" ", "").upper(), expected2.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_having_query(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT Category, SUM(SalesAmount) FROM Sales GROUP BY Category HAVING SUM(SalesAmount) > 1000"
        expected = "SELECT Category, SUM(SalesAmount) FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales GROUP BY Category HAVING SUM(SalesAmount) > 1000"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_nested_exists(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT * FROM Customers c WHERE EXISTS (SELECT 1 FROM Sales s WHERE s.CustomerKey = c.CustomerKey)"
        expected = "SELECT * FROM (SELECT * FROM Customers WHERE Customers.division = 'VCC') AS c WHERE EXISTS (SELECT 1 FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s WHERE s.CustomerKey = c.CustomerKey)"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_outer_joins(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        
        # Test LEFT JOIN, RIGHT JOIN, FULL OUTER JOIN
        for join_type in ["LEFT", "RIGHT", "FULL OUTER"]:
            sql = f"SELECT * FROM Sales s {join_type} JOIN Customers c ON s.CustomerKey = c.CustomerKey"
            expected = f"SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s {join_type} JOIN (SELECT * FROM Customers WHERE Customers.division = 'VCC') AS c ON s.CustomerKey = c.CustomerKey"
            res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
            self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_applies_cross_and_outer(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        
        # Test CROSS APPLY raw table
        sql1 = "SELECT * FROM Sales s CROSS APPLY Orders o WHERE s.OrderId = o.OrderId"
        expected1 = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s CROSS APPLY (SELECT * FROM Orders WHERE Orders.division_code = 'VCC') AS o WHERE s.OrderId = o.OrderId"
        res1 = DivisionRLSEngine.apply_division_rls(sql1, "VCC", "conn_1")
        self.assertEqual(res1.replace(" ", "").upper(), expected1.replace(" ", "").upper())

        # Test OUTER APPLY nested subquery
        sql2 = "SELECT * FROM Sales s OUTER APPLY (SELECT * FROM Orders o WHERE o.OrderId = s.OrderId) o"
        expected2 = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s OUTER APPLY (SELECT * FROM (SELECT * FROM Orders WHERE Orders.division_code = 'VCC') AS o WHERE o.OrderId = s.OrderId) AS o"
        res2 = DivisionRLSEngine.apply_division_rls(sql2, "VCC", "conn_1")
        self.assertEqual(res2.replace(" ", "").upper(), expected2.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_window_function(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT Product, ROW_NUMBER() OVER (PARTITION BY Category ORDER BY SalesAmount DESC) as Rank FROM Sales"
        expected = "SELECT Product, ROW_NUMBER() OVER (PARTITION BY Category ORDER BY SalesAmount DESC) as Rank FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS Sales"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_distinct_top_offset(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        
        # Test DISTINCT
        sql1 = "SELECT DISTINCT s.Category FROM Sales s"
        expected1 = "SELECT DISTINCT s.Category FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s"
        res1 = DivisionRLSEngine.apply_division_rls(sql1, "VCC", "conn_1")
        self.assertEqual(res1.replace(" ", "").upper(), expected1.replace(" ", "").upper())

        # Test TOP 100
        sql2 = "SELECT TOP 100 * FROM Sales s ORDER BY SalesAmount DESC"
        expected2 = "SELECT TOP 100 * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s ORDER BY SalesAmount DESC"
        res2 = DivisionRLSEngine.apply_division_rls(sql2, "VCC", "conn_1")
        self.assertEqual(res2.replace(" ", "").upper(), expected2.replace(" ", "").upper())

        # Test OFFSET FETCH
        sql3 = "SELECT * FROM Sales s ORDER BY SalesAmount OFFSET 10 ROWS FETCH NEXT 10 ROWS ONLY"
        expected3 = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s ORDER BY SalesAmount OFFSET 10 ROWS FETCH NEXT 10 ROWS ONLY"
        res3 = DivisionRLSEngine.apply_division_rls(sql3, "VCC", "conn_1")
        self.assertEqual(res3.replace(" ", "").upper(), expected3.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_multiple_references(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        sql = "SELECT * FROM Sales s1 JOIN Sales s2 ON s1.ProductKey = s2.ProductKey"
        expected = "SELECT * FROM (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s1 JOIN (SELECT * FROM Sales WHERE Sales.division = 'VCC') AS s2 ON s1.ProductKey = s2.ProductKey"
        res = DivisionRLSEngine.apply_division_rls(sql, "VCC", "conn_1")
        self.assertEqual(res.replace(" ", "").upper(), expected.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_alias_and_schema_handling(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        
        # Test dbo.Sales
        sql1 = "SELECT * FROM dbo.Sales s"
        expected1 = "SELECT * FROM (SELECT * FROM dbo.Sales WHERE Sales.division = 'VCC') AS s"
        res1 = DivisionRLSEngine.apply_division_rls(sql1, "VCC", "conn_1")
        self.assertEqual(res1.replace(" ", "").upper(), expected1.replace(" ", "").upper())

        # Test [dbo].[Sales]
        sql2 = "SELECT * FROM [dbo].[Sales] s"
        expected2 = "SELECT * FROM (SELECT * FROM [dbo].[Sales] WHERE Sales.division = 'VCC') AS s"
        res2 = DivisionRLSEngine.apply_division_rls(sql2, "VCC", "conn_1")
        self.assertEqual(res2.replace(" ", "").upper(), expected2.replace(" ", "").upper())

        # Test "Sales"
        sql3 = 'SELECT * FROM "Sales" s'
        expected3 = "SELECT * FROM (SELECT * FROM [Sales] WHERE Sales.division = 'VCC') AS s"
        res3 = DivisionRLSEngine.apply_division_rls(sql3, "VCC", "conn_1")
        self.assertEqual(res3.replace(" ", "").upper(), expected3.replace(" ", "").upper())

    @patch.object(DivisionRLSEngine, 'get_division_tables')
    def test_sql_injection_defense_escaping(self, mock_get_tables):
        mock_get_tables.return_value = self.division_tables
        malicious_code = "VCC'; DROP TABLE Sales; --"
        sql = "SELECT * FROM Sales"
        res = DivisionRLSEngine.apply_division_rls(sql, malicious_code, "conn_1")
        self.assertIn("Sales.division = 'VCC''; DROP TABLE Sales; --'", res)

if __name__ == "__main__":
    unittest.main()
