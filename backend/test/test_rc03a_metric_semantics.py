"""
RC-03a - approved metric business semantics, encoded in configuration.

Approved rulings:
    1. "amount"        -> the order-pending amount metric (OrderPending.Amt)
    2. "bill amount"   -> billamt   (Outstanding.billamt)
    3. "due amount"    -> Pending Amount (Outstanding.PAMT)   [NOT ACHIEVABLE - see below]
  preserved:
    "payment amount"   -> Pending Amount
    "pending amount"   -> Pending Amount
    "sales amount"     -> C Y
    "due"              -> the days metric (OrderPending.due)

Configuration changes made (no code changed):
  - Pending Amount synonyms += "due amount", "payment amount", "outstanding amount"
  - C Y            synonyms += "sales amount"   (its description is already
                                                 "Sales amount for the current year")
  - OrderPending.Amt business_name "Amount" -> "Order Pending Amount",
    synonyms "Amount, Order Pending Amount, order amount, pending order amount"

The rename was necessary and is proven so by test_synonyms_alone_were_not
_sufficient below: business_name matches at Priority 3 (30000) and beats every
synonym (9000) regardless of how much more of the question the synonym
explains - billamt already had "Bill amount" as a synonym and still lost.
Bare "amount" is still owned by the same physical metric through its synonym
list, so ruling 1 is preserved in substance; only the display name changed.

Ruling 3 is NOT achievable by configuration and is deliberately asserted at
its current behaviour so a future RC-03b flips it intentionally rather than
by accident. The blocker is Priority 4: the metric's technical name is
literally "due", so it claims that token at 20000 and the "due amount"
synonym (9000) can never win the phrase. Renaming a technical identifier is
not a meaning change and would decouple it from its column, so it was not
done here.

Tests assert PHYSICAL identity (table.column), not display names, so they do
not re-break if a business name is renamed again.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _db_reachable():
    try:
        import core.config  # noqa
        from database import engine
        with engine.connect():
            return True
    except Exception:
        return False


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestRC03aMetricSemantics(unittest.TestCase):

    ORDER_PENDING_AMT = ("PBI_ENES_ORDER_PENDING_SUMMARY", "Amt")
    BILLAMT = ("PBI_OUTSTANDING_ENES_SUMMARY", "billamt")
    PENDING_AMOUNT = ("PBI_OUTSTANDING_ENES_SUMMARY", "PAMT")
    CY = ("QB_MDJMD_SALES_5YRS_SUMMARY", "CY")
    DUE_DAYS = ("PBI_ENES_ORDER_PENDING_SUMMARY", "due")

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.conn_id = runner.resolve_logical_connection()

    def _metric_identities(self, question):
        res = self.SemanticResolver.resolve(connection_id=self.conn_id, question=question)
        return [(m.get("table_name"), m.get("column_name"))
                for m in (res.get("metric_objects") or [])]

    def _assert_only(self, question, identity):
        got = self._metric_identities(question)
        self.assertEqual(got, [identity], msg="%s -> %s" % (question, got))

    # --- ruling 1: bare "amount" ------------------------------------------
    def test_show_amount(self):
        self._assert_only("Show amount", self.ORDER_PENDING_AMT)

    def test_total_amount(self):
        self._assert_only("Total amount", self.ORDER_PENDING_AMT)

    def test_amount_with_dimension(self):
        self._assert_only("Show amount for Coimbatore city", self.ORDER_PENDING_AMT)

    # --- ruling 2: "bill amount" ------------------------------------------
    def test_show_bill_amount(self):
        self._assert_only("Show bill amount", self.BILLAMT)

    def test_total_bill_amount(self):
        self._assert_only("Total bill amount", self.BILLAMT)

    # --- preserved meanings -----------------------------------------------
    def test_payment_amount(self):
        self._assert_only("Show payment amount", self.PENDING_AMOUNT)

    def test_pending_amount(self):
        self._assert_only("Show pending amount", self.PENDING_AMOUNT)

    def test_sales_amount(self):
        self._assert_only("Show sales amount", self.CY)

    def test_due_is_still_the_days_metric(self):
        self._assert_only("Show due", self.DUE_DAYS)

    def test_due_days_is_still_a_days_metric(self):
        got = self._metric_identities("Show due days")
        self.assertTrue(got, "expected a metric for 'Show due days'")
        for table, column in got:
            self.assertIn(column, ("due", "Duedays", "nodays"),
                          msg="'due days' must resolve a days metric, got %s" % (got,))

    # --- ruling 3: documented as NOT achieved ------------------------------
    def test_due_amount_remains_blocked_by_technical_name_priority(self):
        """
        Ruling 3 ("due amount" -> Pending Amount) is not reachable through
        configuration: the days metric's TECHNICAL NAME is "due", matching at
        Priority 4 (20000) and out-ranking Pending Amount's "due amount"
        synonym (9000). Asserted at current behaviour so RC-03b changes it
        deliberately.
        """
        got = self._metric_identities("Show due amount")
        self.assertIn(self.DUE_DAYS, got)
        self.assertNotIn(self.PENDING_AMOUNT, got)


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestRC03aRenameWasNecessary(unittest.TestCase):
    """
    Evidence for why the business_name rename was required rather than
    optional: a synonym can never outrank a business_name match.
    """

    def test_synonyms_alone_were_not_sufficient(self):
        from semantic.semantic_resolver import _get_match_info

        question = "Show bill amount"
        # billamt matches the longer, more specific phrase - via a synonym.
        bill = _get_match_info("billamt", "billamt",
                               "Bill amount, Actual amount, Cost", question)
        # A metric whose business_name is the bare word "amount" matches at
        # Priority 3 with a SHORTER, less specific match.
        generic = _get_match_info("amt", "Amount", "Amount", question)

        self.assertEqual(bill[3], "Synonym")
        self.assertEqual(bill[0], 9000)
        self.assertEqual(generic[3], "Business Name")
        self.assertEqual(generic[0], 30000)
        self.assertGreater(bill[1], generic[1])       # explains more
        self.assertLess(bill[0], generic[0])          # yet scores lower


if __name__ == "__main__":
    unittest.main()
