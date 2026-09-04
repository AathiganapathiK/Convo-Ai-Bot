"""
RC-03b - generic phrase-level precedence in metric overlap resolution.

_get_match_info's priority tiers (50000..8000) encode WHICH FIELD matched -
technical name, business name, synonym, stem overlap - not how much of the
question that field explained. "due amount" used to resolve to the metric
"due" (Business Name, tier 30000, 3 chars matched) instead of Pending Amount
(Synonym, tier 9000, 10 chars matched: the synonym IS "due amount"), because
cross-candidate overlap resolution compared tiers before length.

SemanticResolver._overlap_sort_key fixes this by comparing matched LENGTH
first within the bracket of genuine configured-phrase evidence (technical
name / business name / synonym, tiers 9000-30000), keeping tier-first
ordering both above it (exact whole-question match, >=40000) and below it
(heuristic stem overlap, <9000).

Nothing here is RC-03b-specific in the code under test: no metric name or
phrase is hardcoded in semantic_resolver.py. Part 1 proves the exact
required cases via live configuration; Part 2 proves the mechanism
generalizes with a synthetic conflict the unit under test has never seen.

Live-connection tests follow test_rc03a_metric_semantics.py's DB-gated
pattern.

    python backend/test/test_rc03b_metric_phrase_precedence.py
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


# =====================================================================
# Part 1 - pure unit tests of the sort key. No database.
# =====================================================================

class TestOverlapSortKeyUnit(unittest.TestCase):
    """
    _overlap_sort_key in isolation, with synthetic candidate dicts standing
    in for whatever metric or dimension configuration produced them. Proves
    the ordering rule itself, independent of any live data.
    """

    @classmethod
    def setUpClass(cls):
        from semantic.semantic_resolver import SemanticResolver
        # Stored as staticmethod() so accessing it via `self.key` does not
        # rebind it as a bound method (Python's descriptor protocol turns a
        # plain function stored as a class attribute into one automatically).
        cls.key = staticmethod(SemanticResolver._overlap_sort_key)

    def _candidate(self, score, length, is_metric=True):
        return {"score": score, "length": length,
                "type": "metric" if is_metric else "dimension"}

    def test_a_longer_synonym_outranks_a_shorter_business_name_match(self):
        # The exact shape of the due/due-amount conflict, with synthetic
        # values: tier 30000 len 3 vs tier 9000 len 10.
        short_business_name = self._candidate(score=30000, length=3)
        long_synonym = self._candidate(score=9000, length=10)
        ordered = sorted(
            [short_business_name, long_synonym], key=self.key, reverse=True
        )
        self.assertIs(ordered[0], long_synonym)

    def test_a_longer_technical_name_phrase_outranks_a_shorter_synonym(self):
        # The rule is symmetric within the bracket - it is about length, not
        # about which field the longer phrase happened to be in.
        long_technical = self._candidate(score=20000, length=12)
        short_synonym = self._candidate(score=9000, length=4)
        ordered = sorted(
            [long_technical, short_synonym], key=self.key, reverse=True
        )
        self.assertIs(ordered[0], long_technical)

    def test_equal_length_within_bracket_falls_back_to_score(self):
        higher_tier = self._candidate(score=20000, length=5)
        lower_tier = self._candidate(score=9000, length=5)
        ordered = sorted([lower_tier, higher_tier], key=self.key, reverse=True)
        self.assertIs(ordered[0], higher_tier)

    def test_exact_whole_question_match_always_wins_regardless_of_length(self):
        # Tier >= 40000 keeps score-first ordering - it is already the
        # strongest possible signal (the ENTIRE question equals the name).
        exact_match_short = self._candidate(score=50000, length=3)
        long_phrase_match = self._candidate(score=9000, length=20)
        ordered = sorted(
            [long_phrase_match, exact_match_short], key=self.key, reverse=True
        )
        self.assertIs(ordered[0], exact_match_short)

    def test_stem_overlap_never_outranks_a_genuine_phrase_match(self):
        # Tier < 9000 (heuristic) keeps score-first ordering and must not be
        # strengthened by this change, even when its matched length is large.
        stem_overlap_long = self._candidate(score=6000, length=15)
        genuine_short_synonym = self._candidate(score=9000, length=3)
        ordered = sorted(
            [stem_overlap_long, genuine_short_synonym], key=self.key, reverse=True
        )
        self.assertIs(ordered[0], genuine_short_synonym)

    def test_metric_still_preferred_over_dimension_on_a_full_tie(self):
        metric = self._candidate(score=9000, length=5, is_metric=True)
        dimension = self._candidate(score=9000, length=5, is_metric=False)
        ordered = sorted([dimension, metric], key=self.key, reverse=True)
        self.assertIs(ordered[0], metric)

    def test_no_conflict_case_is_unaffected(self):
        # A single candidate's ranking is trivially unaffected - the rule
        # only matters when candidates are compared against each other.
        only = self._candidate(score=20000, length=3)
        ordered = sorted([only], key=self.key, reverse=True)
        self.assertEqual(ordered, [only])


# =====================================================================
# Part 2 - live connection, the exact required cases plus RC-03a regression.
# =====================================================================

@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestRC03bRequiredCases(unittest.TestCase):

    PENDING_AMOUNT = ("PBI_OUTSTANDING_ENES_SUMMARY", "PAMT")
    DUE_DAYS = ("PBI_ENES_ORDER_PENDING_SUMMARY", "due")
    ORDER_PENDING_AMT = ("PBI_ENES_ORDER_PENDING_SUMMARY", "Amt")
    BILLAMT = ("PBI_OUTSTANDING_ENES_SUMMARY", "billamt")
    CY = ("QB_MDJMD_SALES_5YRS_SUMMARY", "CY")

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

    # -- 1-4: the required behaviours, verbatim -----------------------------

    def test_1_due_amount_resolves_to_pending_amount(self):
        self._assert_only("Show due amount", self.PENDING_AMOUNT)

    def test_1b_total_due_amount(self):
        self._assert_only("Total due amount", self.PENDING_AMOUNT)

    def test_2_payment_amount_resolves_to_pending_amount(self):
        self._assert_only("Show payment amount", self.PENDING_AMOUNT)

    def test_3_pending_amount_resolves_to_pending_amount(self):
        self._assert_only("Show pending amount", self.PENDING_AMOUNT)

    def test_4_bare_due_still_resolves_to_the_days_metric(self):
        self._assert_only("Show due", self.DUE_DAYS)
        self._assert_only("Total due", self.DUE_DAYS)

    def test_4b_due_amount_for_a_city_still_resolves_correctly(self):
        # A qualified question, proving the fix survives additional tokens
        # around the conflicting phrase.
        self._assert_only("Show due amount for Chennai city", self.PENDING_AMOUNT)

    # -- RC-03a regression: metric resolution unrelated to this fix ---------

    def test_bill_amount_still_resolves_to_billamt(self):
        self._assert_only("Show bill amount", self.BILLAMT)

    def test_sales_amount_still_resolves_to_cy(self):
        self._assert_only("sales amount for Chennai", self.CY)

    def test_bare_amount_still_resolves_to_order_pending_amount(self):
        self._assert_only("Show amount", self.ORDER_PENDING_AMT)


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestGenericPhraseConflictMechanism(unittest.TestCase):
    """
    A synthetic conflict, seeded and torn down, proving the fix generalizes
    to ANY multi-word business metric phrase competing with a single-token
    metric - not only "due amount". Configures a throwaway metric whose
    synonym is a multi-word phrase containing an existing single-token
    metric's name, then asserts the phrase wins.
    """

    @classmethod
    def setUpClass(cls):
        from database import engine
        from sqlalchemy import text
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        from semantic.semantic_resolver import SemanticResolver

        cls.engine = engine
        cls.text = text
        cls.SemanticResolver = SemanticResolver
        cls.conn_id = runner.resolve_logical_connection()

        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT TOP 1 table_name, column_name FROM semantic_metrics
                WHERE connection_id = :c AND is_active = 1 AND is_excluded = 0
            """), {"c": cls.conn_id}).fetchone()
        if not row:
            raise unittest.SkipTest("no active metric available to piggyback the test table on")
        cls.table_name, cls.column_name = row

        # A single-token technical name that, before this fix, would win by
        # tier over any longer synonym phrase containing it.
        cls.short_name = "zzrc03bshort"
        cls.phrase_synonym = "zzrc03bshort qualifier phrase"

        import uuid

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO semantic_metrics
                    (metric_id, connection_id, metric_name, business_name,
                     table_name, column_name, aggregation_type, source,
                     is_active, is_excluded, is_confirmed, synonyms)
                VALUES (:id, :c, :n, :n, :t, :col, 'SUM', 'test', 1, 0, 1, NULL)
            """), {"id": str(uuid.uuid4()), "c": cls.conn_id, "n": cls.short_name,
                   "t": cls.table_name, "col": cls.column_name})

            conn.execute(text("""
                INSERT INTO semantic_metrics
                    (metric_id, connection_id, metric_name, business_name,
                     table_name, column_name, aggregation_type, source,
                     is_active, is_excluded, is_confirmed, synonyms)
                VALUES (:id, :c, :n, :n, :t, :col, 'SUM', 'test', 1, 0, 1, :syn)
            """), {"id": str(uuid.uuid4()), "c": cls.conn_id, "n": "zzrc03blong",
                   "t": cls.table_name, "col": cls.column_name,
                   "syn": cls.phrase_synonym})

    @classmethod
    def tearDownClass(cls):
        with cls.engine.begin() as conn:
            conn.execute(cls.text("""
                DELETE FROM semantic_metrics
                WHERE connection_id = :c AND metric_name IN ('zzrc03bshort', 'zzrc03blong')
            """), {"c": cls.conn_id})

    def test_the_multiword_phrase_wins_over_the_single_token_it_contains(self):
        res = self.SemanticResolver.resolve(
            connection_id=self.conn_id,
            question="Show %s" % self.phrase_synonym,
        )
        names = [m.get("metric_name") for m in (res.get("metric_objects") or [])]
        self.assertIn("zzrc03blong", names)
        self.assertNotIn("zzrc03bshort", names)

    def test_the_short_token_alone_still_resolves_to_itself(self):
        res = self.SemanticResolver.resolve(
            connection_id=self.conn_id,
            question="Show %s" % self.short_name,
        )
        names = [m.get("metric_name") for m in (res.get("metric_objects") or [])]
        self.assertIn("zzrc03bshort", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
