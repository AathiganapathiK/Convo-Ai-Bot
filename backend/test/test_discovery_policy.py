"""
Gate 2 Step 12 - the rules discovery follows.

Written against the real evidence, because that is what defeated the obvious
implementations. Every threshold here was chosen after looking at the live
profile, and the comments record which column would break if it moved.
"""

import unittest

from semantic.discovery_policy import (
    DiscoveryPolicy,
    detect_semantic_category,
    is_own_category,
    tokenize,
)


def _policy_with(evidence=None, **kwargs):
    policy = DiscoveryPolicy("conn-1")
    for key, value in (evidence or {}).items():
        policy.evidence[key] = value
    for name, value in kwargs.items():
        setattr(policy, name, value)
    return policy


def _ev(distinct, rows):
    return {"distinct_count": distinct, "row_count": rows, "samples": [], "data_type": "int"}


class TestMetricRejection(unittest.TestCase):
    """
    The live numbers these rules were built against:

        ID       2,238,958 of 2,238,958 rows  100.0% unique
        OrderNo     29,188 of    36,617 rows   79.7% unique
        Docnum      55,133 of    95,613 rows   57.7% unique
        Sno             13 of 2,238,958 rows    0.0% unique
        DocMonth        12 of 2,238,958 rows    0.0% unique
    """

    def test_fully_unique_numeric_is_an_identifier(self):
        policy = _policy_with({("t", "id"): _ev(2238958, 2238958)})
        self.assertIn("identifies rows", policy.rejects_as_metric("t", "ID"))

    def test_low_cardinality_over_a_huge_table_is_a_label(self):
        # Sno: 13 values across 2.2 million rows. Uniqueness alone would call
        # this a measure, which is how it became one.
        policy = _policy_with({("t", "sno"): _ev(13, 2238958)})
        self.assertIn("code or a label", policy.rejects_as_metric("t", "Sno"))

    def test_month_number_is_a_label(self):
        policy = _policy_with({("t", "docmonth"): _ev(12, 2238958)})
        self.assertIsNotNone(policy.rejects_as_metric("t", "DocMonth"))

    def test_partly_unique_identifier_is_caught_by_its_name(self):
        # OrderNo is only 79.7% unique and Docnum 57.7%, so no uniqueness
        # threshold that spares real measures would catch either. The name
        # token does.
        policy = _policy_with({("t", "orderno"): _ev(29188, 36617)})
        self.assertIn("identifier token", policy.rejects_as_metric("t", "OrderNo"))

        policy = _policy_with({("t", "docnum"): _ev(55133, 95613)})
        self.assertIn("identifier token", policy.rejects_as_metric("t", "Docnum"))

    def test_nodays_survives_although_its_name_contains_no(self):
        # The regression that forces token matching instead of substring
        # matching. "Nodays" is a genuine measure on the receivables table.
        policy = _policy_with({("t", "nodays"): _ev(400, 95613)})
        self.assertIsNone(policy.rejects_as_metric("t", "nodays"))

    def test_real_measures_are_kept(self):
        policy = _policy_with({
            ("t", "cy"): _ev(93691, 2238958),
            ("t", "pytd"): _ev(66138, 2238958),
            ("t", "billamt"): _ev(40000, 95613),
        })
        for column in ("CY", "PYTD", "billamt"):
            self.assertIsNone(policy.rejects_as_metric("t", column), column)

    def test_configured_period_column_is_never_a_measure(self):
        policy = _policy_with(period_label_columns={("t", "invmonth")})
        self.assertIn("labels a period", policy.rejects_as_metric("t", "InvMonth"))

    def test_small_table_is_not_mistaken_for_a_label(self):
        # 12 distinct across 20 rows is just a small table, not a code set.
        policy = _policy_with({("t", "amount"): _ev(12, 20)})
        self.assertIsNone(policy.rejects_as_metric("t", "amount"))

    def test_no_evidence_falls_back_to_the_name_only(self):
        policy = _policy_with()
        self.assertIsNone(policy.rejects_as_metric("t", "Revenue"))
        self.assertIsNotNone(policy.rejects_as_metric("t", "CustomerId"))


class TestDateExpansion(unittest.TestCase):

    def test_only_the_configured_column_expands(self):
        policy = _policy_with(date_columns={"orders": "DocDate"})

        self.assertTrue(policy.should_expand_date("orders", "DocDate"))
        self.assertTrue(policy.should_expand_date("ORDERS", "docdate"))
        self.assertFalse(policy.should_expand_date("orders", "DueDate"))

    def test_no_configuration_means_no_expansion(self):
        # Deliberately not "fall back to anything date-typed". That fallback
        # turned six date columns into thirty-six dimensions.
        policy = _policy_with()
        self.assertFalse(policy.should_expand_date("sales", "createddate"))

    def test_a_constant_column_is_not_a_dimension(self):
        # createddate: one value across 2.2 million rows, an ETL load stamp.
        policy = _policy_with({("sales", "createddate"): _ev(1, 2238958)})
        self.assertTrue(policy.is_constant_column("sales", "createddate"))

    def test_a_one_row_table_is_not_a_constant_column(self):
        policy = _policy_with({("t", "c"): _ev(1, 1)})
        self.assertFalse(policy.is_constant_column("t", "c"))


class TestSemanticCategory(unittest.TestCase):

    def test_table_name_does_not_reach_the_category(self):
        # Every one of these came back Finance because their table is called
        # QB_MDJMD_SALES_5YRS_SUMMARY and "sales" was tokenised into the same
        # set as the column name.
        for column in ("ProdGrp1", "MktType", "RMNAME", "STG"):
            self.assertNotEqual(detect_semantic_category(column), "Finance", column)

    def test_a_column_that_says_nothing_gets_other_not_a_guess(self):
        self.assertEqual(detect_semantic_category("ProdGrp1"), "Other")

    def test_real_signals_still_work(self):
        self.assertEqual(detect_semantic_category("State1"), "Geography")
        self.assertEqual(detect_semantic_category("InvMonth"), "Time")
        self.assertEqual(detect_semantic_category("Category"), "Product")

    def test_our_own_values_may_be_recomputed(self):
        for value in ("Finance", "Other", "Geography", "UNKNOWN", None):
            self.assertTrue(is_own_category(value), value)

    def test_a_value_we_could_not_have_written_is_someone_elses(self):
        # A person chose LOCATION_COUNTRY. Recomputing it would discard their
        # work, whether or not they went on to press Confirm.
        self.assertFalse(is_own_category("LOCATION_COUNTRY"))


class TestTokenize(unittest.TestCase):

    def test_camel_and_snake_split(self):
        self.assertEqual(tokenize("OrderNo"), {"order", "no"})
        self.assertEqual(tokenize("MKT_RM"), {"mkt", "rm"})

    def test_a_single_word_is_not_split_into_its_letters(self):
        # If "Nodays" split into {no, days} the substring bug would come back
        # through the token door.
        self.assertEqual(tokenize("Nodays"), {"nodays"})


class TestDecisionsAreRespected(unittest.TestCase):

    def test_confirmed_and_excluded_lookups_are_case_insensitive(self):
        policy = _policy_with(
            confirmed_metrics={("sales", "cy")},
            confirmed_dimensions={("sales", "rmname", "rmname")},
            excluded_columns={("sales", "createddate")},
        )

        self.assertTrue(policy.is_confirmed_metric("SALES", "CY"))
        self.assertTrue(policy.is_confirmed_dimension("Sales", "RMNAME", "rmname"))
        self.assertTrue(policy.is_excluded("SALES", "CreatedDate"))
        self.assertFalse(policy.is_confirmed_metric("sales", "py"))


if __name__ == "__main__":
    unittest.main()
