import unittest
import datetime
from semantic.temporal.models import TimeCapability, YearRange
from semantic.temporal.capability_cache import TimeResolutionCache, CapabilityCacheEntry
from semantic.temporal.enums import TimeStrategyType


class TestCapabilityCache(unittest.TestCase):

    def setUp(self):
        # Reset cache state before each test
        TimeResolutionCache.clear()

    def tearDown(self):
        # Reset cache state after each test
        TimeResolutionCache.clear()

    def test_put_and_get(self):
        # Test 1: put() -> get() returns same object.
        conn_id = "conn_1"
        cap = TimeCapability(
            date_columns=["OrderDate"],
            available_year_range=YearRange(min_year=2020, max_year=2025)
        )
        
        entry = TimeResolutionCache.put(
            connection_id=conn_id,
            capability=cap,
            preferred_strategy=TimeStrategyType.DATE_COLUMN
        )
        
        cached = TimeResolutionCache.get(conn_id)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.connection_id, conn_id)
        self.assertEqual(cached.capability, cap)
        self.assertEqual(cached.preferred_strategy, TimeStrategyType.DATE_COLUMN)
        self.assertIsInstance(cached.created_at, datetime.datetime)
        self.assertIsInstance(cached.last_accessed, datetime.datetime)

    def test_invalidate(self):
        # Test 2: invalidate() -> get() -> None
        conn_id = "conn_2"
        cap = TimeCapability(date_columns=["OrderDate"])
        TimeResolutionCache.put(conn_id, cap)
        
        # Ensure it exists
        self.assertIsNotNone(TimeResolutionCache.get(conn_id))
        
        # Invalidate
        TimeResolutionCache.invalidate(conn_id)
        self.assertIsNone(TimeResolutionCache.get(conn_id))

    def test_clear(self):
        # Test 3: clear() -> cache empty
        TimeResolutionCache.put("conn_a", TimeCapability())
        TimeResolutionCache.put("conn_b", TimeCapability())
        
        self.assertEqual(len(TimeResolutionCache._cache), 2)
        
        TimeResolutionCache.clear()
        self.assertEqual(len(TimeResolutionCache._cache), 0)

    def test_different_connections(self):
        # Test 4: Different connections -> Different cache entries
        cap_1 = TimeCapability(date_columns=["ColA"])
        cap_2 = TimeCapability(date_columns=["ColB"])
        
        TimeResolutionCache.put("conn_1", cap_1, TimeStrategyType.SNAPSHOT)
        TimeResolutionCache.put("conn_2", cap_2, TimeStrategyType.DATE_COLUMN)
        
        entry_1 = TimeResolutionCache.get("conn_1")
        entry_2 = TimeResolutionCache.get("conn_2")
        
        self.assertEqual(entry_1.capability.date_columns, ["ColA"])
        self.assertEqual(entry_2.capability.date_columns, ["ColB"])
        self.assertEqual(entry_1.preferred_strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(entry_2.preferred_strategy, TimeStrategyType.DATE_COLUMN)

    def test_schema_sync_invalidation(self):
        # Test 5: Schema sync -> invalidate() -> rebuild -> new capability returned
        conn_id = "conn_sync_test"
        old_cap = TimeCapability(date_columns=["OldDateColumn"])
        
        # Store initial capability in cache
        TimeResolutionCache.put(conn_id, old_cap, TimeStrategyType.DATE_COLUMN)
        
        # Verify it is returned from cache
        self.assertEqual(TimeResolutionCache.get(conn_id).capability.date_columns, ["OldDateColumn"])
        
        # Invalidate (simulating SchemaSyncService.sync_schema)
        TimeResolutionCache.invalidate(conn_id)
        self.assertIsNone(TimeResolutionCache.get(conn_id))
        
        # Rebuild/Re-put new capability
        new_cap = TimeCapability(date_columns=["NewDateColumn"])
        TimeResolutionCache.put(conn_id, new_cap, TimeStrategyType.DATE_COLUMN)
        
        # Verify new capability is returned
        cached = TimeResolutionCache.get(conn_id)
        self.assertEqual(cached.capability.date_columns, ["NewDateColumn"])

    def test_resolver_cache_integration(self):
        from semantic.temporal import TimeStrategyResolver, CurrentYearIntent
        resolver = TimeStrategyResolver()
        ref_date = datetime.date(2026, 8, 5)
        intent = CurrentYearIntent(reference_date=ref_date)
        
        cap = TimeCapability(
            date_columns=["OrderDate"],
            calendar_tables=["DimCalendar"]
        )
        conn_id = "resolver_conn"
        
        # 1. Resolve with capability and connection_id (first run)
        plan = resolver.resolve(intent, capability=cap, connection_id=conn_id)
        self.assertEqual(plan.strategy, TimeStrategyType.CALENDAR_DIMENSION)
        
        # Verify it cached the capability and preferred strategy
        cached = TimeResolutionCache.get(conn_id)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.capability, cap)
        self.assertEqual(cached.preferred_strategy, TimeStrategyType.CALENDAR_DIMENSION)
        
        # 2. Mutate cached capability columns and verify resolver uses cached version without passing it
        cached.capability.date_columns = ["MutatedOrderDate"]
        
        # Resolve again without passing capability
        plan_cached = resolver.resolve(intent, connection_id=conn_id)
        self.assertEqual(plan_cached.date_column, "MutatedOrderDate")
        self.assertEqual(plan_cached.strategy, TimeStrategyType.CALENDAR_DIMENSION)


if __name__ == "__main__":
    unittest.main()
