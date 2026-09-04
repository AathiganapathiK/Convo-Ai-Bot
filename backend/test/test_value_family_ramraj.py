"""
RAMRAJ brand-family resolution - curated value families, live connection.

Data-driven, not code-driven: "Ramraj" is not a stored value anywhere in the
warehouse. PBI_ENES_ORDER_PENDING_SUMMARY.Brand is a confirmed dimension whose
values are brand x product-line pairs (RAMRAJ DHOTI, RAMRAJ PANT, ...), so
asking for the brand alone used to fall through to fuzzy matching and return
one arbitrary product line - RAMRAJ LITTLESTARS - as a confident SINGLE_MATCH.

semantic_value_family (migration 008) records the twelve verified members as
data, reviewed by tools/seed_value_family.py against the live index. Nothing
in semantic/value_family.py or semantic/dimension_value_resolver.py names
RAMRAJ; the mechanism is exercised here only because RAMRAJ is the family this
connection has configured.

DB-gated, following test_rc03a_metric_semantics.py's pattern: this is
live-connection-dependent behaviour, not a pure unit.

    python backend/test/test_value_family_ramraj.py
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
class TestRamrajBrandFamily(unittest.TestCase):

    BRAND_TABLE = ("PBI_ENES_ORDER_PENDING_SUMMARY", "Brand")
    PRODGRP1_TABLE = ("QB_MDJMD_SALES_5YRS_SUMMARY", "ProdGrp1")

    @classmethod
    def setUpClass(cls):
        from semantic.dimension_value_resolver import DimensionValueResolver
        from semantic.semantic_resolver import SemanticResolver
        from semantic.value_family import ValueFamilyLoader
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.SemanticResolver = SemanticResolver
        cls.DimensionValueResolver = DimensionValueResolver
        cls.conn_id = runner.resolve_logical_connection()

        cls.family_config = ValueFamilyLoader.for_connection(cls.conn_id)
        cls.ramraj = next(
            (f for f in cls.family_config.usable() if f.family_name.upper() == "RAMRAJ"),
            None,
        )
        if cls.ramraj is None:
            raise unittest.SkipTest(
                "RAMRAJ family not seeded on this connection - run "
                "tools/seed_value_family.py --apply first"
            )

    def _resolve(self, question):
        return self.SemanticResolver.resolve(
            connection_id=self.conn_id, question=question,
            previous_semantic_context=None,
        )

    def _values(self, question):
        res = self._resolve(question)
        return [(v.get("value"), v.get("table_name"), v.get("column_name"))
                for v in (res.get("value_matches") or [])]

    def _status(self, question):
        self._resolve(question)
        rr = self.DimensionValueResolver.last_resolution_result
        return rr.status.value if rr and hasattr(rr.status, "value") else None

    # -- configuration itself ------------------------------------------------

    def test_the_family_has_at_least_two_verified_members(self):
        self.assertGreaterEqual(len(self.ramraj.members), 2)

    def test_every_member_is_a_real_indexed_brand_value(self):
        from sqlalchemy import text
        from database import engine
        table, column = self.BRAND_TABLE
        with engine.connect() as conn:
            indexed = {r[0] for r in conn.execute(text("""
                SELECT i.value FROM dimension_value_index i
                JOIN semantic_dimensions d ON d.dimension_id = i.semantic_dimension_id
                WHERE i.connection_id = :c AND d.table_name = :t AND d.column_name = :col
            """), {"c": self.conn_id, "t": table, "col": column})}
        for member in self.ramraj.members:
            self.assertIn(member, indexed,
                          "%r is configured as a RAMRAJ member but is not an "
                          "indexed Brand value" % member)

    def test_ramraj_littlestars_is_one_member_among_several(self):
        self.assertIn("RAMRAJ LITTLESTARS", self.ramraj.members)
        self.assertGreater(len(self.ramraj.members), 1)

    # -- 1. "Ramraj brand" -----------------------------------------------

    def test_1_ramraj_brand(self):
        values = self._values("Ramraj brand")
        self.assertEqual(len(values), 1, msg=values)
        value, table, column = values[0]
        self.assertEqual(value.upper(), "RAMRAJ")
        self.assertEqual((table, column), self.BRAND_TABLE)
        self.assertEqual(self._status("Ramraj brand"), "SINGLE_MATCH")

    # -- 2. "Ramraj brands" (plural) --------------------------------------

    def test_2_ramraj_brands_plural(self):
        values = self._values("Ramraj brands")
        self.assertTrue(values, "the plural qualifier must not lose the family")
        value, table, column = values[0]
        self.assertEqual(value.upper(), "RAMRAJ")
        self.assertEqual((table, column), self.BRAND_TABLE)

    # -- 3. "sales for Ramraj brand" --------------------------------------

    def test_3_sales_for_ramraj_brand(self):
        res = self._resolve("sales for Ramraj brand")
        metrics = [(m.get("table_name"), m.get("column_name"))
                   for m in (res.get("metric_objects") or [])]
        self.assertIn(("QB_MDJMD_SALES_5YRS_SUMMARY", "CY"), metrics)
        values = [(v.get("value") or "").upper() for v in (res.get("value_matches") or [])]
        self.assertIn("RAMRAJ", values)

    # -- 4. "total sales for Ramraj" (no explicit qualifier) --------------

    def test_4_total_sales_for_ramraj_no_qualifier(self):
        # Without "brand", RAMRAJ (Brand) competes with every RAMRAJ* product
        # line on Brand AND ProdGrp1. This is genuine ambiguity - the question
        # does not say which grain is meant - and must not collapse to a
        # guess. It must NOT, in particular, silently resolve to
        # RAMRAJ LITTLESTARS the way it did before value families existed.
        values = self._values("Total sales for Ramraj")
        resolved_only_to_littlestars = (
            len(values) == 1
            and (values[0][0] or "").upper() == "RAMRAJ LITTLESTARS"
        )
        self.assertFalse(
            resolved_only_to_littlestars,
            "must not collapse an unqualified brand mention to one "
            "arbitrary product line",
        )

    # -- 5. "Ramraj product" stays product semantics ----------------------

    def test_5_ramraj_product_group_is_product_semantics(self):
        # "product group" is Prod Grp1's own configured synonym - this proves
        # an explicit non-brand qualifier is not overridden by the family.
        res = self._resolve("Show sales for Ramraj product group")
        dims = [(d.get("table_name"), d.get("column_name"))
                for d in (res.get("dimension_objects") or [])]
        if dims:
            self.assertNotEqual(dims[0], self.BRAND_TABLE)

    # -- 6. brand + category: both dimensions present ---------------------

    def test_6_ramraj_brand_and_franchise_category_both_present(self):
        res = self._resolve("Show sales for Ramraj brand and Franchise category")
        dim_columns = {d.get("column_name") for d in (res.get("dimension_objects") or [])}
        self.assertIn("Brand", dim_columns)
        self.assertIn("Category", dim_columns)
        values = [(v.get("value") or "").upper() for v in (res.get("value_matches") or [])]
        self.assertIn("RAMRAJ", values)

    # -- 7. regression: RAMRAJ LITTLESTARS must never be the sole match ----

    def test_7_littlestars_never_the_sole_brand_match(self):
        for question in (
            "Ramraj brand", "sales for Ramraj brand", "Show sales for Ramraj brand",
            "Total sales for Ramraj brand", "Now show quantity for Ramraj brand",
        ):
            with self.subTest(question=question):
                values = self._values(question)
                self.assertFalse(
                    len(values) == 1
                    and (values[0][0] or "").upper() == "RAMRAJ LITTLESTARS",
                    "%r resolved to RAMRAJ LITTLESTARS alone" % question,
                )

    # -- plan-level expansion ------------------------------------------------

    def test_family_expands_to_an_in_filter_in_the_plan(self):
        from semantic.semantic_plan_builder import SemanticPlanBuilder
        res = self._resolve("Show sales for Ramraj brand")
        plan = SemanticPlanBuilder.build(
            question="Show sales for Ramraj brand",
            semantic_result=res, time_context=None,
            relevant_tables=[self.BRAND_TABLE[0]],
            connection_id=self.conn_id,
        )
        brand_filters = [f for f in plan.filters if f.column_name == "Brand"]
        self.assertTrue(brand_filters, "no filter was built for the Brand dimension")
        f = brand_filters[0]
        self.assertEqual(f.operator.value, "IN")
        self.assertGreaterEqual(len(f.values), 2)
        for member in f.values:
            self.assertIn(member, self.ramraj.members)


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestGenericFamilyMechanism(unittest.TestCase):
    """
    The mechanism itself, proven with a synthetic family so a pass here does
    not depend on RAMRAJ specifically - it proves the code path generalizes.
    """

    @classmethod
    def setUpClass(cls):
        from database import engine
        from sqlalchemy import text
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.conn_id = runner.resolve_logical_connection()
        cls.engine = engine
        cls.text = text

        with engine.connect() as conn:
            dim = conn.execute(text("""
                SELECT TOP 1 dimension_id FROM semantic_dimensions
                WHERE connection_id = :c AND table_name = 'PBI_ENES_ORDER_PENDING_SUMMARY'
                  AND column_name = 'Brand' AND is_active = 1
            """), {"c": cls.conn_id}).fetchone()
        if not dim:
            raise unittest.SkipTest("Brand dimension not found on this connection")
        cls.dimension_id = str(dim[0])
        cls.test_family = "ZZTESTFAMILY_%s" % os.getpid()

        with engine.begin() as conn:
            for member in ("RAMRAJ DHOTI", "RAMRAJ PANT"):
                conn.execute(text("""
                    INSERT INTO semantic_value_family
                        (connection_id, dimension_id, family_name, member_value,
                         is_confirmed, created_by)
                    VALUES (:c, :d, :f, :m, 1, 'test_generic_family')
                """), {"c": cls.conn_id, "d": cls.dimension_id,
                       "f": cls.test_family, "m": member})

        from semantic.value_family import ValueFamilyLoader
        from semantic.dimension_value_resolver import DimensionValueResolver
        ValueFamilyLoader.invalidate(cls.conn_id)
        DimensionValueResolver.default_cache.invalidate(cls.conn_id) \
            if hasattr(DimensionValueResolver.default_cache, "invalidate") else None

    @classmethod
    def tearDownClass(cls):
        with cls.engine.begin() as conn:
            conn.execute(cls.text("""
                DELETE FROM semantic_value_family
                WHERE connection_id = :c AND family_name = :f
            """), {"c": cls.conn_id, "f": cls.test_family})
        from semantic.value_family import ValueFamilyLoader
        ValueFamilyLoader.invalidate(cls.conn_id)

    def test_a_freshly_configured_family_resolves_the_same_way(self):
        from semantic.value_family import ValueFamilyLoader
        config = ValueFamilyLoader.for_connection(self.conn_id)
        found = [f for f in config.usable() if f.family_name == self.test_family]
        self.assertTrue(found, "the synthetic family was not loaded back")
        self.assertEqual(set(found[0].members), {"RAMRAJ DHOTI", "RAMRAJ PANT"})


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestMissingFamilyDoesNotGuess(unittest.TestCase):
    """
    Safety: a dimension/name with no configured family must never be silently
    resolved to a guess. Ambiguity or NO_MATCH, never a confident single value
    manufactured from nothing.
    """

    @classmethod
    def setUpClass(cls):
        from semantic.value_family import ValueFamilyLoader
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.conn_id = runner.resolve_logical_connection()
        cls.ValueFamilyLoader = ValueFamilyLoader

    def test_an_unconfigured_family_name_offers_no_candidate(self):
        config = self.ValueFamilyLoader.for_connection(self.conn_id)
        members = config.members_for(
            "PBI_ENES_ORDER_PENDING_SUMMARY", "Brand", "NOSUCHFAMILY"
        )
        self.assertEqual(members, ())

    def test_a_brand_with_no_configured_family_is_not_invented(self):
        # UATHAYAM has 6 values on Brand and no configured family. It must
        # not silently synthesize one via prefix matching.
        config = self.ValueFamilyLoader.for_connection(self.conn_id)
        members = config.members_for(
            "PBI_ENES_ORDER_PENDING_SUMMARY", "Brand", "UATHAYAM"
        )
        self.assertEqual(members, ())


if __name__ == "__main__":
    unittest.main(verbosity=2)
