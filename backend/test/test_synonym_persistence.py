import unittest
from unittest.mock import patch
from semantic.config_service import SuggestionService
from semantic.config_schema import MetricConfigRequest, DimensionConfigRequest


class TestSynonymPersistence(unittest.TestCase):

    def test_naming_with_reviewer_edits_replaces_synonyms(self):
        """Reviewer edits should be authoritative and not merge old existing synonyms."""
        existing = "Amount, Order Pending Amount"
        proposal = {
            "business_name": "Amt",
            "synonyms": ["Amount", "Pending Amt"]
        }
        # When is_edited is True: old 'Order Pending Amount' must not be resurrected
        result = SuggestionService._naming(proposal, existing_synonyms=existing, is_edited=True)
        self.assertEqual(result.get("synonyms"), "Amount, Pending Amt")

    def test_naming_with_reviewer_edits_allows_clearing_synonyms(self):
        """Reviewer clearing all synonyms should produce an empty string, not restore old ones."""
        existing = "Amount, Order Pending Amount"
        proposal = {
            "business_name": "Amt",
            "synonyms": []
        }
        result = SuggestionService._naming(proposal, existing_synonyms=existing, is_edited=True)
        self.assertEqual(result.get("synonyms"), "")

    def test_naming_without_edits_preserves_additive_merge(self):
        """Unedited raw machine proposal should additively merge with existing synonyms."""
        existing = "Amount, Order Pending Amount"
        proposal = {
            "business_name": "Amt",
            "synonyms": ["total", "value"]
        }
        result = SuggestionService._naming(proposal, existing_synonyms=existing, is_edited=False)
        self.assertEqual(result.get("synonyms"), "Amount, Order Pending Amount, total, value")

    def test_metric_and_dimension_config_request_schemas(self):
        """Ensure schemas accept business_name, description, and synonyms."""
        m = MetricConfigRequest(business_name="Sales", description="Total sales", synonyms="rev, turnover")
        d = DimensionConfigRequest(business_name="Region", description="Sales region", synonyms="zone, area")
        self.assertEqual(m.synonyms, "rev, turnover")
        self.assertEqual(m.business_name, "Sales")
        self.assertEqual(d.synonyms, "zone, area")
        self.assertEqual(d.business_name, "Region")


if __name__ == "__main__":
    unittest.main()
