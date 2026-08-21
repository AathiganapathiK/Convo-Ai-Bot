import unittest
import uuid
from sqlalchemy import text
from database import engine
from fastapi import HTTPException
from services.provider_admin_service import ProviderAdminService
from admin.provider_management import create_model, update_model, CreateModelRequest, UpdateModelRequest

class TestModelRegistrationCapabilities(unittest.TestCase):

    def setUp(self):
        # Create a unique test company to guarantee absolute tenant isolation
        self.company_id = str(uuid.uuid4()).upper()
        self.prov_id = str(uuid.uuid4()).upper()
        
        with engine.begin() as conn:
            # Create company first to satisfy FK constraint
            comp_code = f"TEST_REG_{str(uuid.uuid4())[:8].upper()}"
            conn.execute(text("""
                INSERT INTO companies (company_id, company_code, company_name, timezone, currency, date_format, sql_dialect, is_active)
                VALUES (:c_id, :comp_code, 'Test Registration Company', 'Asia/Kolkata', 'INR', 'DD/MM/YYYY', 'mssql', 1)
            """), {"c_id": self.company_id, "comp_code": comp_code})
            
            # Create provider
            conn.execute(text("""
                INSERT INTO llm_providers (provider_id, company_id, provider_name, provider_type, base_url, is_active)
                VALUES (:p_id, :c_id, 'Test Reg Provider', 'openai', 'https://api.openai.com/v1', 1)
            """), {"p_id": self.prov_id, "c_id": self.company_id})

    def tearDown(self):
        # Completely clean up test data using our company_id scope
        with engine.begin() as conn:
            conn.execute(
                text("""
                DELETE FROM provider_health 
                WHERE provider_id IN (SELECT provider_id FROM llm_providers WHERE company_id = :c_id)
                """),
                {"c_id": self.company_id}
            )
            conn.execute(
                text("DELETE FROM llm_fallbacks WHERE company_id = :c_id"),
                {"c_id": self.company_id}
            )
            conn.execute(
                text("""
                DELETE FROM llm_models 
                WHERE provider_id IN (SELECT provider_id FROM llm_providers WHERE company_id = :c_id)
                """),
                {"c_id": self.company_id}
            )
            conn.execute(
                text("DELETE FROM llm_providers WHERE company_id = :c_id"),
                {"c_id": self.company_id}
            )
            conn.execute(
                text("DELETE FROM companies WHERE company_id = :c_id"),
                {"c_id": self.company_id}
            )

    def test_multiple_purposes_create_multiple_rows(self):
        user_mock = {"company_id": self.company_id}
        
        # Register a model with multiple capabilities (purposes)
        req = CreateModelRequest(
            provider_id=self.prov_id,
            model_name="multi-purpose-model",
            purposes=["sql_generation", "insight", "intent"]
        )
        
        res = create_model(req, user=user_mock)
        self.assertEqual(res["message"], "Model created")
        
        # Verify exactly 3 rows are inserted in the database
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT purpose FROM llm_models WHERE provider_id = :p_id AND model_name = :name"),
                {"p_id": self.prov_id, "name": "multi-purpose-model"}
            ).fetchall()
            
        purposes = {r.purpose for r in rows}
        self.assertEqual(len(rows), 3)
        self.assertEqual(purposes, {"sql_generation", "insight", "intent"})

    def test_duplicate_purpose_does_not_create_duplicate_rows(self):
        user_mock = {"company_id": self.company_id}
        
        # Create initial row
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO llm_models (model_id, provider_id, model_name, purpose, is_default, is_active)
                VALUES (:m_id, :p_id, 'dup-test-model', 'sql_generation', 0, 1)
            """), {"m_id": str(uuid.uuid4()).upper(), "p_id": self.prov_id})
            
        # Register same model with duplicates in list, including the existing one
        req = CreateModelRequest(
            provider_id=self.prov_id,
            model_name="dup-test-model",
            purposes=["sql_generation", "insight", "insight"]
        )
        
        create_model(req, user=user_mock)
        
        # Verify only missing 'insight' is added, and no duplicates exist
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT purpose FROM llm_models WHERE provider_id = :p_id AND model_name = :name"),
                {"p_id": self.prov_id, "name": "dup-test-model"}
            ).fetchall()
            
        purposes = [r.purpose for r in rows]
        self.assertEqual(len(rows), 2)
        self.assertIn("sql_generation", purposes)
        self.assertIn("insight", purposes)

    def test_invalid_purpose_rejected(self):
        user_mock = {"company_id": self.company_id}
        
        # Try to register an invalid purpose
        req = CreateModelRequest(
            provider_id=self.prov_id,
            model_name="invalid-model",
            purposes=["sql_generation", "invalid_purpose"]
        )
        
        with self.assertRaises(HTTPException) as ctx:
            create_model(req, user=user_mock)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid execution purpose", ctx.exception.detail)

    def test_tenant_isolation_preserved(self):
        # Create a second company
        other_company_id = str(uuid.uuid4()).upper()
        other_prov_id = str(uuid.uuid4()).upper()
        
        with engine.begin() as conn:
            comp_code = f"TEST_REG_{str(uuid.uuid4())[:8].upper()}"
            conn.execute(text("""
                INSERT INTO companies (company_id, company_code, company_name, timezone, currency, date_format, sql_dialect, is_active)
                VALUES (:c_id, :comp_code, 'Other Company', 'Asia/Kolkata', 'INR', 'DD/MM/YYYY', 'mssql', 1)
            """), {"c_id": other_company_id, "comp_code": comp_code})
            
            conn.execute(text("""
                INSERT INTO llm_providers (provider_id, company_id, provider_name, provider_type, base_url, is_active)
                VALUES (:p_id, :c_id, 'Other Provider', 'openai', 'https://api.openai.com/v1', 1)
            """), {"p_id": other_prov_id, "c_id": other_company_id})

        try:
            user_mock = {"company_id": self.company_id}
            
            # Try to register a model associated with the other company's provider
            req = CreateModelRequest(
                provider_id=other_prov_id,
                model_name="isolation-model",
                purposes=["sql_generation"]
            )
            
            with self.assertRaises(HTTPException) as ctx:
                create_model(req, user=user_mock)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("Provider not found or access denied", ctx.exception.detail)
            
        finally:
            # Clean up second company
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM llm_models WHERE provider_id = :p_id"), {"p_id": other_prov_id})
                conn.execute(text("DELETE FROM llm_providers WHERE provider_id = :p_id"), {"p_id": other_prov_id})
                conn.execute(text("DELETE FROM companies WHERE company_id = :c_id"), {"c_id": other_company_id})

    def test_fallback_routing_safety_constraint(self):
        user_mock = {"company_id": self.company_id}
        model_id = str(uuid.uuid4()).upper()
        fallback_id = str(uuid.uuid4()).upper()
        
        with engine.begin() as conn:
            # Create model
            conn.execute(text("""
                INSERT INTO llm_models (model_id, provider_id, model_name, purpose, is_default, is_active)
                VALUES (:m_id, :p_id, 'safety-model', 'sql_generation', 0, 1)
            """), {"m_id": model_id, "p_id": self.prov_id})
            
            # Create active fallback referencing this model
            conn.execute(text("""
                INSERT INTO llm_fallbacks (fallback_id, company_id, purpose, priority_order, model_id, is_active)
                VALUES (:f_id, :c_id, 'sql_generation', 1, :m_id, 1)
            """), {"f_id": fallback_id, "c_id": self.company_id, "m_id": model_id})

        # Update model to REMOVE sql_generation capability
        req = UpdateModelRequest(
            model_name="safety-model",
            purposes=["insight"], # sql_generation is removed
            is_active=True
        )
        
        # Verify update is rejected with 400 because of routing reference
        with self.assertRaises(HTTPException) as ctx:
            update_model(model_id, req, user=user_mock)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("active in fallback routing", ctx.exception.detail)

    def test_existing_single_purpose_compatible(self):
        user_mock = {"company_id": self.company_id}
        
        # Test creating via single 'purpose' field
        req = CreateModelRequest(
            provider_id=self.prov_id,
            model_name="single-purpose-compat-model",
            purpose="sql_generation"
        )
        
        create_model(req, user=user_mock)
        
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT purpose FROM llm_models WHERE provider_id = :p_id AND model_name = :name"),
                {"p_id": self.prov_id, "name": "single-purpose-compat-model"}
            ).fetchone()
        self.assertEqual(row.purpose, "sql_generation")
