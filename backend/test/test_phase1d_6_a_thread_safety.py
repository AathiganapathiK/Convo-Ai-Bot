import sys
import os
import unittest
import threading
import time
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching.models import ResolutionStatus, CachedDimensionValue
from semantic.matching import STOPWORDS, SingularPluralMatcher


def make_mock_val(dim_id, bus_name, tbl, col, val):
    import re
    def normalize(text):
        if not text: return ""
        t = text.lower().strip()
        t = t.replace("'", "")
        t = re.sub(r'[-_/\.]', ' ', t)
        return t
        
    norm_val_raw = normalize(val)
    val_tokens = [t for t in norm_val_raw.split() if t not in STOPWORDS]
    val_singulars = [SingularPluralMatcher._to_singular(t) for t in val_tokens]
    
    return CachedDimensionValue(
        semantic_dimension_id=dim_id,
        business_name=bus_name,
        table_name=tbl,
        column_name=col,
        value=val,
        normalized_value=val.lower(),
        runtime_stored_norm=norm_val_raw,
        runtime_stored_tokens=val_tokens,
        runtime_stored_singulars=val_singulars,
        runtime_raw_norm=norm_val_raw,
        runtime_raw_tokens=val_tokens,
        runtime_raw_singulars=val_singulars
    )


class TestPhase1D6AThreadSafety(unittest.TestCase):

    def setUp(self):
        # Build mock dataset containing:
        # - City: Coimbatore, Chennai
        # - Brand: Linen Pant, Ramraj Pant, Ramraj Shirt, Ramraj
        # - District: Coimbatore
        # - Prod Grp: Ramraj
        self.mock_db_values = [
            make_mock_val(101, "City", "PBI_CITY", "CityName", "Coimbatore"),
            make_mock_val(101, "City", "PBI_CITY", "CityName", "Chennai"),
            make_mock_val(201, "Brand", "PBI_BRAND", "BrandName", "Linen Pant"),
            make_mock_val(201, "Brand", "PBI_BRAND", "BrandName", "Linen Shirt"),
            make_mock_val(201, "Brand", "PBI_BRAND", "BrandName", "Ramraj Pant"),
            make_mock_val(201, "Brand", "PBI_BRAND", "BrandName", "Ramraj Shirt"),
            make_mock_val(201, "Brand", "PBI_BRAND", "BrandName", "Ramraj"),
            make_mock_val(301, "District", "PBI_DISTRICT", "DistrictName", "Coimbatore"),
            make_mock_val(401, "Prod Grp", "PBI_PROD_GRP", "ProdGrpName", "Ramraj")
        ]
        
        # Dimension Context mimicking database schemas
        self.dimension_context = [
            {"dimension_name": "City", "business_name": "City", "table_name": "PBI_CITY", "column_name": "CityName"},
            {"dimension_name": "Brand", "business_name": "Brand", "table_name": "PBI_BRAND", "column_name": "BrandName"},
            {"dimension_name": "District", "business_name": "District", "table_name": "PBI_DISTRICT", "column_name": "DistrictName"},
            {"dimension_name": "Prod Grp", "business_name": "Prod Grp", "table_name": "PBI_PROD_GRP", "column_name": "ProdGrpName"}
        ]
        
        # Patch the dimension value loader globally
        self.loader_patcher = patch.object(DimensionValueResolver, "_load_dimension_values", return_value=self.mock_db_values)
        self.mock_loader = self.loader_patcher.start()

    def tearDown(self):
        self.loader_patcher.stop()

    def test_concurrent_resolutions_metadata_isolation(self):
        """
        TEST 1 & 4: Run 50 concurrent request pairs to verify that Request A (City/Coimbatore)
        and Request B (Brand/Linen) are fully isolated and do not cross-contaminate.
        Validates request-local properties: resolution_result, followup_context, match_stats.
        """
        num_pairs = 50
        
        def run_request_a(idx):
            # Slow down slightly to increase race condition overlap
            time.sleep(0.001 * (idx % 10))
            res = DimensionValueResolver.resolve(
                "conn_a",
                "Coimbatore city",
                dimension_context=self.dimension_context
            )
            # Since "Coimbatore" matches City and District, but "city" explicitly filters to City:
            # results should have Coimbatore for City
            return {
                "idx": idx,
                "type": "A",
                "results": res,
                "stats": res.match_stats,
                "res_result": res.resolution_result,
                "followup": res.followup_context
            }

        def run_request_b(idx):
            time.sleep(0.001 * (idx % 10))
            res = DimensionValueResolver.resolve(
                "conn_b",
                "linen brand",
                dimension_context=self.dimension_context
            )
            # matches Brand/Linen Pant and Brand/Linen Shirt
            return {
                "idx": idx,
                "type": "B",
                "results": res,
                "stats": res.match_stats,
                "res_result": res.resolution_result,
                "followup": res.followup_context
            }

        tasks = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            for i in range(num_pairs):
                tasks.append(executor.submit(run_request_a, i))
                tasks.append(executor.submit(run_request_b, i))

        results_a = []
        results_b = []
        for future in as_completed(tasks):
            result = future.result()
            if result["type"] == "A":
                results_a.append(result)
            else:
                results_b.append(result)

        self.assertEqual(len(results_a), num_pairs)
        self.assertEqual(len(results_b), num_pairs)

        # Assert isolation for Request A
        for item in results_a:
            res = item["results"]
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["business_name"], "City")
            self.assertEqual(res[0]["value"], "Coimbatore")
            
            # Check properties are request-local and isolated
            res_result = item["res_result"]
            self.assertIsNotNone(res_result)
            self.assertEqual(res_result.status, ResolutionStatus.SINGLE_MATCH)
            self.assertEqual(res_result.dominant_match.result.value, "Coimbatore")
            self.assertEqual(res_result.dominant_match.result.business_name, "City")

        # Assert isolation for Request B
        for item in results_b:
            res = item["results"]
            # Ramraj Pant and Ramraj Shirt are both Brand, and "brand" explicitly filters to Brand.
            # However, "Ramraj" matches both: "Ramraj Pant" and "Ramraj Shirt" within the Brand dimension.
            # This causes a SAME_DIMENSION STRONG_AMBIGUITY!
            self.assertEqual(len(res), 2)
            for r in res:
                self.assertEqual(r["business_name"], "Brand")
            
            res_result = item["res_result"]
            self.assertIsNotNone(res_result)
            self.assertEqual(res_result.status, ResolutionStatus.STRONG_AMBIGUITY)
            self.assertIsNone(res_result.dominant_match)
            self.assertEqual(len(res_result.candidates), 2)

    def test_concurrent_status_isolation(self):
        """
        TEST 2: Request A produces STRONG_AMBIGUITY ("pant"),
        Request B produces SINGLE_MATCH ("Chennai").
        Verify neither thread receives the other's status or candidates.
        """
        num_pairs = 50
        
        def run_request_a(idx):
            time.sleep(0.001 * (idx % 10))
            # "pant" matches Linen Pant and Ramraj Pant (both Brand) -> STRONG_AMBIGUITY
            res = DimensionValueResolver.resolve(
                "conn_a",
                "pant",
                dimension_context=self.dimension_context
            )
            return {
                "results": res,
                "res_result": res.resolution_result,
                "status": res.resolution_result.status
            }

        def run_request_b(idx):
            time.sleep(0.001 * (idx % 10))
            # "Chennai" matches only City/Chennai -> SINGLE_MATCH
            res = DimensionValueResolver.resolve(
                "conn_b",
                "Chennai",
                dimension_context=self.dimension_context
            )
            return {
                "results": res,
                "res_result": res.resolution_result,
                "status": res.resolution_result.status
            }

        tasks = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            for i in range(num_pairs):
                tasks.append(executor.submit(run_request_a, i))
                tasks.append(executor.submit(run_request_b, i))

        for future in as_completed(tasks):
            item = future.result()
            # If it was a Chennai request, it must be SINGLE_MATCH
            if len(item["results"]) == 1 and item["results"][0]["value"] == "Chennai":
                self.assertEqual(item["status"], ResolutionStatus.SINGLE_MATCH)
                self.assertEqual(item["res_result"].dominant_match.result.value, "Chennai")
            else:
                # Must be pant request -> STRONG_AMBIGUITY
                self.assertEqual(item["status"], ResolutionStatus.STRONG_AMBIGUITY)
                self.assertIsNone(item["res_result"].dominant_match)

    def test_concurrent_followup_context_isolation(self):
        """
        TEST 3: Request A resolves elliptical follow-up with previous dimension context for City.
        Request B resolves elliptical follow-up with previous dimension context for Brand.
        Verify followup contexts remain isolated.
        """
        num_pairs = 50
        
        # Previous context for A: City = Chennai, Metric = Qty
        prev_context_a = {
            "metrics": [{"business_name": "Qty"}],
            "dimensions": [{"business_name": "City", "value": "Chennai"}],
            "resolved_values": [{"dimension_id": 101, "business_name": "City", "value": "Chennai"}]
        }
        # Previous context for B: Brand = Ramraj, Metric = Sales
        prev_context_b = {
            "metrics": [{"business_name": "Sales"}],
            "dimensions": [{"business_name": "Brand", "value": "Ramraj"}],
            "resolved_values": [{"dimension_id": 201, "business_name": "Brand", "value": "Ramraj"}]
        }

        def run_request_a(idx):
            time.sleep(0.001 * (idx % 10))
            res = DimensionValueResolver.resolve(
                "conn_a",
                "what about Coimbatore?",
                dimension_context=self.dimension_context,
                previous_semantic_context=prev_context_a,
                current_metrics=[{"business_name": "Qty"}] # Same metric
            )
            return {
                "results": res,
                "followup": res.followup_context
            }

        def run_request_b(idx):
            time.sleep(0.001 * (idx % 10))
            res = DimensionValueResolver.resolve(
                "conn_b",
                "what about Ramraj?",
                dimension_context=self.dimension_context,
                previous_semantic_context=prev_context_b,
                current_metrics=[{"business_name": "Sales"}] # Same metric
            )
            return {
                "results": res,
                "followup": res.followup_context
            }

        tasks = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            for i in range(num_pairs):
                tasks.append(executor.submit(run_request_a, i))
                tasks.append(executor.submit(run_request_b, i))

        for future in as_completed(tasks):
            item = future.result()
            followup = item["followup"]
            self.assertIsNotNone(followup)
            
            # Identify which request it was
            first_val = item["results"][0]["value"]
            if first_val == "Coimbatore":
                # Request A: followup should show City inherited
                self.assertTrue(followup["applied"])
                self.assertEqual(followup["previous_dimension"].lower(), "city")
            elif first_val == "Ramraj":
                # Request B: followup should show Brand inherited
                self.assertTrue(followup["applied"])
                self.assertEqual(followup["previous_dimension"].lower(), "brand")
            else:
                self.fail(f"Unexpected resolved value: {first_val}")

    def test_concurrent_match_stats_isolation(self):
        """
        TEST 5: Verify match_stats cannot cross-contaminate.
        """
        num_pairs = 50
        
        def run_request(idx):
            time.sleep(0.001 * (idx % 10))
            res = DimensionValueResolver.resolve(
                "conn",
                "Chennai",
                dimension_context=self.dimension_context
            )
            return {
                "results": res,
                "stats": res.match_stats
            }

        tasks = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            for i in range(num_pairs):
                tasks.append(executor.submit(run_request, i))

        for future in as_completed(tasks):
            item = future.result()
            stats = item["stats"]
            self.assertIsNotNone(stats)
            self.assertTrue(stats.exact_attempted or stats.normalized_attempted)

    def test_backward_compatibility_class_attributes(self):
        """
        Verify that class-level properties (DimensionValueResolver.last_resolution_result,
        last_followup_context, last_match_stats) are thread-local and backward-compatible.
        Also runs concurrent requests to verify class attributes remain isolated across threads.
        """
        # 1. Main thread check
        res = DimensionValueResolver.resolve(
            "conn_bcomp",
            "Coimbatore city",
            dimension_context=self.dimension_context
        )
        
        self.assertIsNotNone(DimensionValueResolver.last_resolution_result)
        self.assertIsNotNone(DimensionValueResolver.last_match_stats)
        self.assertEqual(DimensionValueResolver.last_resolution_result, res.resolution_result)
        self.assertEqual(DimensionValueResolver.last_match_stats, res.match_stats)
        self.assertEqual(DimensionValueResolver.last_followup_context, res.followup_context)

        # 2. Concurrency check on thread-local properties
        q = queue.Queue()
        
        def run_thread(q, query, is_a):
            res_thread = DimensionValueResolver.resolve(
                "conn_thread",
                query,
                dimension_context=self.dimension_context
            )
            q.put({
                "is_a": is_a,
                "res": res_thread,
                "class_res": DimensionValueResolver.last_resolution_result,
                "class_stats": DimensionValueResolver.last_match_stats,
                "class_followup": DimensionValueResolver.last_followup_context
            })
            
        t1 = threading.Thread(target=run_thread, args=(q, "Coimbatore city", True))
        t2 = threading.Thread(target=run_thread, args=(q, "ramraj brand", False))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        # Verify thread local storage isolation:
        # Each thread's class properties should match its local result object, not the other thread's.
        thread_results = [q.get(), q.get()]
        for tr in thread_results:
            self.assertEqual(tr["class_res"], tr["res"].resolution_result)
            self.assertEqual(tr["class_stats"], tr["res"].match_stats)
            self.assertEqual(tr["class_followup"], tr["res"].followup_context)


if __name__ == "__main__":
    unittest.main()
