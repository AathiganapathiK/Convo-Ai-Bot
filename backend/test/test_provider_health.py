import unittest
import uuid
from sqlalchemy import text
from database import engine
from services.provider_health_service import ProviderHealthService

class TestProviderHealth(unittest.TestCase):

    def setUp(self):
        # Create a unique test company to guarantee absolute tenant isolation
        self.company_id = str(uuid.uuid4()).upper()
        self.prov_id = str(uuid.uuid4()).upper()
        
        with engine.begin() as conn:
            # Create company first to satisfy FK constraint
            comp_code = f"TEST_HLTH_{str(uuid.uuid4())[:8].upper()}"
            conn.execute(text("""
                INSERT INTO companies (company_id, company_code, company_name, timezone, currency, date_format, sql_dialect, is_active)
                VALUES (:c_id, :comp_code, 'Test Health Company', 'Asia/Kolkata', 'INR', 'DD/MM/YYYY', 'mssql', 1)
            """), {"c_id": self.company_id, "comp_code": comp_code})
            
            # Create provider
            conn.execute(text("""
                INSERT INTO llm_providers (provider_id, company_id, provider_name, provider_type, base_url, is_active)
                VALUES (:p_id, :c_id, 'Test Health Provider', 'openai', 'https://api.openai.com/v1', 1)
            """), {"p_id": self.prov_id, "c_id": self.company_id})

    def tearDown(self):
        # Clean up test data
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM provider_health WHERE provider_id = :p_id"),
                {"p_id": self.prov_id}
            )
            conn.execute(
                text("DELETE FROM llm_providers WHERE provider_id = :p_id"),
                {"p_id": self.prov_id}
            )
            conn.execute(
                text("DELETE FROM companies WHERE company_id = :c_id"),
                {"c_id": self.company_id}
            )

    def test_provider_health_success_and_failure_counters(self):
        # 1. Trigger failure first
        ProviderHealthService.mark_failure_by_id(self.prov_id, "Connection Timeout Error")
        
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT status, failure_count, consecutive_failures, last_error, last_failure_at FROM provider_health WHERE provider_id = :p_id"),
                {"p_id": self.prov_id}
            ).fetchone()
            
        self.assertEqual(row.status, "FAILED")
        self.assertEqual(row.failure_count, 1)
        self.assertEqual(row.consecutive_failures, 1)
        self.assertIn("Connection Timeout Error", row.last_error)
        self.assertIsNotNone(row.last_failure_at)

        # 2. Trigger consecutive failure
        ProviderHealthService.mark_failure_by_id(self.prov_id, "Rate Limit Exceeded")
        
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT status, failure_count, consecutive_failures, last_error FROM provider_health WHERE provider_id = :p_id"),
                {"p_id": self.prov_id}
            ).fetchone()
            
        self.assertEqual(row.status, "FAILED")
        self.assertEqual(row.failure_count, 2)
        self.assertEqual(row.consecutive_failures, 2)
        self.assertIn("Rate Limit Exceeded", row.last_error)

        # 3. Trigger success (should reset consecutive_failures to 0, but preserve failure_count)
        ProviderHealthService.mark_success_by_id(self.prov_id, 145.5)
        
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT status, failure_count, consecutive_failures, average_response_ms, last_success_at FROM provider_health WHERE provider_id = :p_id"),
                {"p_id": self.prov_id}
            ).fetchone()
            
        self.assertEqual(row.status, "HEALTHY")
        self.assertEqual(row.failure_count, 2)  # preserved
        self.assertEqual(row.consecutive_failures, 0)  # reset
        self.assertEqual(row.average_response_ms, 145.5)
        self.assertIsNotNone(row.last_success_at)
