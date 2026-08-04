import sys
import os
import unittest

# Adjust Python path to resolve the 'ai' package from the backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.ast.parser import SQLASTParser
from ai.ast.metadata import SQLASTMetadataExtractor
from ai.ast.schema import SQLASTSchemaValidator
from ai.ast.security import SQLASTSecurityValidator
from ai.repair.engine import RepairEngine
from ai.validation_pipeline import ValidationPipeline


class TestASTRepairEngine(unittest.TestCase):
    def setUp(self):
        self.parser = SQLASTParser()
        self.extractor = SQLASTMetadataExtractor()
        self.validator = SQLASTSchemaValidator()
        self.security_validator = SQLASTSecurityValidator()
        self.pipeline = ValidationPipeline(
            self.parser,
            self.security_validator,
            self.extractor,
            self.validator,
        )
        self.engine = RepairEngine(self.pipeline)
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

    def run_repair(self, sql: str) -> str | None:
        """Helper to run parser, extractor, validator, and if invalid, repair it."""
        pipeline_result = self.pipeline.validate(sql, self.schema_metadata)
        if pipeline_result.passed:
            return sql

        repair_result = self.engine.repair_query(
            pipeline_result, self.schema_metadata
        )
        if repair_result.success:
            return repair_result.repaired_sql
        return None

    def parse_repaired(self, repaired_sql: str):
        """Helper to parse a repaired SQL query and return its extracted metadata."""
        context = self.parser.parse(repaired_sql)
        self.assertEqual(context.errors, [])
        self.assertIsNotNone(context.ast, f"Failed to parse repaired SQL: {repaired_sql}")
        metadata = self.extractor.extract(context.ast)
        validation_result = self.validator.validate(metadata, self.schema_metadata)
        self.assertTrue(
            validation_result.passed,
            f"Repaired SQL failed schema validation: {validation_result.errors}",
        )
        return metadata

    def test_column_name_similarity_repair(self):
        # "Sale" should be corrected to "Sales" on the "Sales" table
        sql = "SELECT Sale FROM Sales"
        repaired = self.run_repair(sql)
        self.assertIsNotNone(repaired)
        metadata = self.parse_repaired(repaired)
        self.assertEqual(metadata.selected_columns[0].name.lower(), "sales")

    def test_table_name_similarity_repair(self):
        # "Product" should be corrected to "Products"
        sql = "SELECT Product FROM Product"
        repaired = self.run_repair(sql)
        self.assertIsNotNone(repaired)
        metadata = self.parse_repaired(repaired)
        self.assertEqual(metadata.tables[0].name.lower(), "products")

    def test_alias_repair(self):
        # "X.Sales" has invalid prefix "X". It should be repaired to "S.Sales" since "S" is the alias of "Sales"
        sql = "SELECT X.Sales FROM Sales S"
        repaired = self.run_repair(sql)
        self.assertIsNotNone(repaired)
        metadata = self.parse_repaired(repaired)
        self.assertEqual(metadata.selected_columns[0].table.lower(), "s")
        self.assertEqual(metadata.selected_columns[0].name.lower(), "sales")

    def test_ambiguity_repair(self):
        # ProductKey is in both Sales and Products. It should qualify it using primary table alias S.
        sql = "SELECT ProductKey FROM Sales S JOIN Products P ON S.ProductKey = P.ProductKey"
        repaired = self.run_repair(sql)
        self.assertIsNotNone(repaired)
        metadata = self.parse_repaired(repaired)
        self.assertEqual(metadata.selected_columns[0].table.lower(), "s")
        self.assertEqual(metadata.selected_columns[0].name.lower(), "productkey")

    def test_compound_repair_multi_step(self):
        # Query has both a table name error and a column name error:
        # "SELECT Pricee FROM Product" -> should resolve Product to Products, and Pricee to Price
        sql = "SELECT Pricee FROM Product"
        repaired = self.run_repair(sql)
        self.assertIsNotNone(repaired)
        metadata = self.parse_repaired(repaired)
        self.assertEqual(metadata.tables[0].name.lower(), "products")
        self.assertEqual(metadata.selected_columns[0].name.lower(), "price")

    def test_unrepairable_query(self):
        # Totally invalid column name that has no close similarity matches
        sql = "SELECT xyz123abc FROM Sales"
        repaired = self.run_repair(sql)
        self.assertIsNone(repaired)

    def test_strategy_order(self):
        names = [type(strategy).__name__ for strategy in self.engine.strategies]
        self.assertEqual(
            names,
            [
                "ColumnRepair",
                "TableRepair",
                "AliasRepair",
                "AmbiguityRepair",
            ],
        )

    def test_repair_result_fields(self):
        sql = "SELECT Sale FROM Sales"
        pipeline_result = self.pipeline.validate(sql, self.schema_metadata)
        repair_result = self.engine.repair_query(
            pipeline_result, self.schema_metadata
        )
        self.assertTrue(repair_result.success)
        self.assertTrue(repair_result.repaired)
        self.assertIsNotNone(repair_result.final_context)
        self.assertIsNotNone(repair_result.final_validation)
        self.assertTrue(repair_result.final_validation.passed)
        self.assertGreater(repair_result.attempts, 0)
        self.assertEqual(len(repair_result.applied_repairs), 1)
        self.assertEqual(repair_result.status, "REPAIRED")
        self.assertGreaterEqual(repair_result.duration_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
