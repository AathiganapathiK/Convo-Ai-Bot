"""
semantic/value_family.py - the config layer, no database.

Mirrors test_snapshot_config_table_aware.py's approach: _load is stubbed so
this runs anywhere.

    python backend/test/test_value_family_config.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.value_family import (  # noqa: E402
    ValueFamily,
    ValueFamilyConfig,
    ValueFamilyLoader,
)

CONN = "conn-1"
TABLE = "PBI_ENES_ORDER_PENDING_SUMMARY"
COLUMN = "Brand"


def fake_load_two_families(cls, connection_id):
    return ValueFamilyConfig(families=[
        ValueFamily(
            family_name="RAMRAJ", dimension_id="dim-1", business_name="Brand",
            table_name=TABLE, column_name=COLUMN,
            members=("RAMRAJ PANT", "RAMRAJ SHIRT", "RAMRAJ LITTLESTARS"),
        ),
        ValueFamily(
            family_name="SINGLETON", dimension_id="dim-1", business_name="Brand",
            table_name=TABLE, column_name=COLUMN,
            members=("SINGLETON ONLY",),
        ),
    ])


class StubbedBase(unittest.TestCase):
    def setUp(self):
        ValueFamilyLoader.invalidate(None)
        self._real_load = ValueFamilyLoader._load
        ValueFamilyLoader._load = classmethod(fake_load_two_families)

    def tearDown(self):
        ValueFamilyLoader._load = self._real_load
        ValueFamilyLoader.invalidate(None)


class TestUsability(StubbedBase):

    def test_a_family_with_multiple_members_is_usable(self):
        config = ValueFamilyLoader.for_connection(CONN)
        names = {f.family_name for f in config.usable()}
        self.assertIn("RAMRAJ", names)

    def test_a_single_member_family_is_not_usable(self):
        """One member is a rename, not a family - offering it as a value
        would put a name in front of the user that resolves to something
        narrower than it claims."""
        config = ValueFamilyLoader.for_connection(CONN)
        names = {f.family_name for f in config.usable()}
        self.assertNotIn("SINGLETON", names)

    def test_an_empty_family_is_not_usable(self):
        empty = ValueFamily(family_name="EMPTY", dimension_id="d",
                            business_name="B", table_name=TABLE,
                            column_name=COLUMN, members=())
        self.assertFalse(empty.is_usable)


class TestMembersFor(StubbedBase):

    def test_members_for_the_configured_family(self):
        config = ValueFamilyLoader.for_connection(CONN)
        members = config.members_for(TABLE, COLUMN, "RAMRAJ")
        self.assertEqual(set(members),
                         {"RAMRAJ PANT", "RAMRAJ SHIRT", "RAMRAJ LITTLESTARS"})

    def test_lookup_is_case_insensitive_on_the_family_name(self):
        config = ValueFamilyLoader.for_connection(CONN)
        self.assertEqual(
            config.members_for(TABLE, COLUMN, "ramraj"),
            config.members_for(TABLE, COLUMN, "RAMRAJ"),
        )

    def test_a_different_table_with_the_same_name_returns_nothing(self):
        # A family is scoped to its physical dimension - it must not leak to
        # a different table that happens to share the family name.
        config = ValueFamilyLoader.for_connection(CONN)
        members = config.members_for("SOME_OTHER_TABLE", COLUMN, "RAMRAJ")
        self.assertEqual(members, ())

    def test_an_unconfigured_name_returns_nothing(self):
        config = ValueFamilyLoader.for_connection(CONN)
        self.assertEqual(config.members_for(TABLE, COLUMN, "NOSUCHFAMILY"), ())

    def test_missing_arguments_return_nothing(self):
        config = ValueFamilyLoader.for_connection(CONN)
        self.assertEqual(config.members_for(None, COLUMN, "RAMRAJ"), ())
        self.assertEqual(config.members_for(TABLE, None, "RAMRAJ"), ())
        self.assertEqual(config.members_for(TABLE, COLUMN, None), ())


class TestNoConfigurationDoesNotGuess(unittest.TestCase):

    def test_no_connection_returns_an_empty_config(self):
        config = ValueFamilyLoader.for_connection(None)
        self.assertFalse(config.is_configured)
        self.assertEqual(config.usable(), [])

    def test_a_load_failure_returns_an_empty_config_not_an_exception(self):
        def boom(cls, connection_id):
            raise RuntimeError("database unavailable")

        ValueFamilyLoader.invalidate(None)
        real = ValueFamilyLoader._load
        ValueFamilyLoader._load = classmethod(boom)
        try:
            config = ValueFamilyLoader.for_connection(CONN)
            self.assertFalse(config.is_configured)
        finally:
            ValueFamilyLoader._load = real
            ValueFamilyLoader.invalidate(None)


class TestCache(StubbedBase):

    def test_invalidate_clears_the_connection(self):
        ValueFamilyLoader.for_connection(CONN)
        self.assertIn(CONN, ValueFamilyLoader._cache)
        ValueFamilyLoader.invalidate(CONN)
        self.assertNotIn(CONN, ValueFamilyLoader._cache)


if __name__ == "__main__":
    unittest.main(verbosity=2)
