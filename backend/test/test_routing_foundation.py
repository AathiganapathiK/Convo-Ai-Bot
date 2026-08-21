import unittest
import uuid
from sqlalchemy import text
from database import engine
from fastapi import HTTPException
from unittest.mock import patch, MagicMock

from services.provider_admin_service import ProviderAdminService
from services.fallback_service import FallbackService
from ai.providers.provider_factory import ProviderFactory
from ai.providers.groq_provider import GroqProvider
from ai.providers.ollama_provider import OllamaProvider
from ai.providers.openai_provider import OpenAIProvider

class TestRoutingFoundation(unittest.TestCase):

    def setUp(self):
        # Create a unique test company to guarantee absolute tenant isolation
        self.company_id = str(uuid.uuid4()).upper()
        self.purpose = "sql_generation"
        
        # Insert test active provider
        self.prov_active_id = str(uuid.uuid4()).upper()
        # Insert test inactive provider
        self.prov_inactive_id = str(uuid.uuid4()).upper()
        
        # Insert test models
        self.model_a_id = str(uuid.uuid4()).upper()  # Active
        self.model_b_id = str(uuid.uuid4()).upper()  # Active
        self.model_inactive_id = str(uuid.uuid4()).upper() # Inactive
        
        with engine.begin() as conn:
            # Create company first to satisfy FK constraint
            comp_code = f"TEST_{str(uuid.uuid4())[:8].upper()}"
            conn.execute(text("""
                INSERT INTO companies (company_id, company_code, company_name, timezone, currency, date_format, sql_dialect, is_active)
                VALUES (:c_id, :comp_code, 'Test Company', 'Asia/Kolkata', 'INR', 'DD/MM/YYYY', 'mssql', 1)
            """), {"c_id": self.company_id, "comp_code": comp_code})
            
            # Create active provider
            conn.execute(text("""
                INSERT INTO llm_providers (provider_id, company_id, provider_name, provider_type, base_url, is_active)
                VALUES (:p_id, :c_id, 'Test Active Prov', 'openai', 'https://api.openai.com/v1', 1)
            """), {"p_id": self.prov_active_id, "c_id": self.company_id})
            
            # Create inactive provider
            conn.execute(text("""
                INSERT INTO llm_providers (provider_id, company_id, provider_name, provider_type, base_url, is_active)
                VALUES (:p_id, :c_id, 'Test Inactive Prov', 'groq', 'https://api.groq.com', 0)
            """), {"p_id": self.prov_inactive_id, "c_id": self.company_id})
            
            # Create active models
            conn.execute(text("""
                INSERT INTO llm_models (model_id, provider_id, model_name, purpose, is_default, is_active)
                VALUES (:m_id, :p_id, 'model-active-a', :purp, 0, 1)
            """), {"m_id": self.model_a_id, "p_id": self.prov_active_id, "purp": self.purpose})
            
            conn.execute(text("""
                INSERT INTO llm_models (model_id, provider_id, model_name, purpose, is_default, is_active)
                VALUES (:m_id, :p_id, 'model-active-b', :purp, 0, 1)
            """), {"m_id": self.model_b_id, "p_id": self.prov_active_id, "purp": self.purpose})
            
            # Create inactive model under active provider
            conn.execute(text("""
                INSERT INTO llm_models (model_id, provider_id, model_name, purpose, is_default, is_active)
                VALUES (:m_id, :p_id, 'model-inactive', :purp, 0, 0)
            """), {"m_id": self.model_inactive_id, "p_id": self.prov_active_id, "purp": self.purpose})

    def tearDown(self):
        # Completely clean up test data using our company_id scope
        with engine.begin() as conn:
            # Delete from provider_health referencing test providers
            conn.execute(
                text("""
                DELETE FROM provider_health 
                WHERE provider_id IN (SELECT provider_id FROM llm_providers WHERE company_id = :c_id)
                """),
                {"c_id": self.company_id}
            )
            # Delete from llm_fallbacks
            conn.execute(
                text("DELETE FROM llm_fallbacks WHERE company_id = :c_id"),
                {"c_id": self.company_id}
            )
            # Delete from llm_models
            conn.execute(
                text("""
                DELETE FROM llm_models 
                WHERE provider_id IN (SELECT provider_id FROM llm_providers WHERE company_id = :c_id)
                """),
                {"c_id": self.company_id}
            )
            # Delete from llm_providers
            conn.execute(
                text("DELETE FROM llm_providers WHERE company_id = :c_id"),
                {"c_id": self.company_id}
            )
            # Delete from companies last to avoid FK constraint violations
            conn.execute(
                text("DELETE FROM companies WHERE company_id = :c_id"),
                {"c_id": self.company_id}
            )

    def test_1_set_primary_model_updates_fallbacks(self):
        # 1. Setting primary model updates llm_fallbacks priority 1
        success = ProviderAdminService.set_default_model(self.company_id, self.purpose, self.model_a_id)
        self.assertTrue(success)
        
        # Verify fallback table has it at priority 1
        fallbacks = FallbackService.get_models_for_purpose(self.purpose, self.company_id)
        self.assertEqual(len(fallbacks), 1)
        self.assertEqual(fallbacks[0]["model_name"], "model-active-a")
        self.assertEqual(fallbacks[0]["priority_order"], 1)

    def test_2_fallback_priority_shifting(self):
        # Make Model A default
        ProviderAdminService.set_default_model(self.company_id, self.purpose, self.model_a_id)
        
        # Make Model B default -> Model A should be shifted to priority 2
        ProviderAdminService.set_default_model(self.company_id, self.purpose, self.model_b_id)
        
        fallbacks = FallbackService.get_models_for_purpose(self.purpose, self.company_id)
        self.assertEqual(len(fallbacks), 2)
        
        # First model should be B
        self.assertEqual(fallbacks[0]["model_name"], "model-active-b")
        self.assertEqual(fallbacks[0]["priority_order"], 1)
        
        # Second model should be shifted to A
        self.assertEqual(fallbacks[1]["model_name"], "model-active-a")
        self.assertEqual(fallbacks[1]["priority_order"], 2)

    def test_3_fallback_priority_swapping(self):
        # Make Model A default
        ProviderAdminService.set_default_model(self.company_id, self.purpose, self.model_a_id)
        # Make Model B default -> B is at 1, A is at 2
        ProviderAdminService.set_default_model(self.company_id, self.purpose, self.model_b_id)
        
        # Make Model A default again -> should swap them: A at 1, B at 2
        ProviderAdminService.set_default_model(self.company_id, self.purpose, self.model_a_id)
        
        fallbacks = FallbackService.get_models_for_purpose(self.purpose, self.company_id)
        self.assertEqual(len(fallbacks), 2)
        self.assertEqual(fallbacks[0]["model_name"], "model-active-a")
        self.assertEqual(fallbacks[0]["priority_order"], 1)
        self.assertEqual(fallbacks[1]["model_name"], "model-active-b")
        self.assertEqual(fallbacks[1]["priority_order"], 2)

    def test_4_duplicate_model_registration_rejected(self):
        # Creating a duplicate (provider, model_name, purpose) violates the UNIQUE constraint
        with self.assertRaises(Exception):
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO llm_models (provider_id, model_name, purpose, is_default, is_active)
                    VALUES (:p_id, 'model-active-a', :purp, 0, 1)
                """), {"p_id": self.prov_active_id, "purp": self.purpose})

    def test_5_duplicate_fallback_priority_rejected(self):
        # Setting two fallbacks to priority 1 violates our filtered unique index
        # We manually insert a priority 1 fallback, then try to insert another priority 1 active fallback
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO llm_fallbacks (company_id, purpose, priority_order, model_id, is_active)
                VALUES (:c_id, :purp, 1, :m_id, 1)
            """), {"c_id": self.company_id, "purp": self.purpose, "m_id": self.model_a_id})
            
        with self.assertRaises(Exception):
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO llm_fallbacks (company_id, purpose, priority_order, model_id, is_active)
                    VALUES (:c_id, :purp, 1, :m_id, 1)
                """), {"c_id": self.company_id, "purp": self.purpose, "m_id": self.model_b_id})

    def test_6_inactive_model_cannot_become_primary(self):
        # Inactive model must be rejected with 400
        with self.assertRaises(HTTPException) as ctx:
            ProviderAdminService.set_default_model(self.company_id, self.purpose, self.model_inactive_id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_7_inactive_provider_cannot_be_used(self):
        # We insert a model under the inactive provider
        inactive_prov_model_id = str(uuid.uuid4()).upper()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO llm_models (model_id, provider_id, model_name, purpose, is_default, is_active)
                VALUES (:m_id, :p_id, 'model-inactive-provider', :purp, 0, 1)
            """), {"m_id": inactive_prov_model_id, "p_id": self.prov_inactive_id, "purp": self.purpose})
            
        try:
            with self.assertRaises(HTTPException) as ctx:
                ProviderAdminService.set_default_model(self.company_id, self.purpose, inactive_prov_model_id)
            self.assertEqual(ctx.exception.status_code, 400)
        finally:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM llm_models WHERE model_id = :id"), {"id": inactive_prov_model_id})

    def test_8_company_isolation(self):
        # Company C trying to set Company A's model
        other_company_id = str(uuid.uuid4()).upper()
        with self.assertRaises(HTTPException) as ctx:
            ProviderAdminService.set_default_model(other_company_id, self.purpose, self.model_a_id)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_9_provider_factory_hardening(self):
        # Unknown provider type raises ValueError
        with self.assertRaises(ValueError):
            ProviderFactory.get_provider("invalid_provider_type")

        # Whitelisted types function correctly
        prov_groq = ProviderFactory.get_provider("groq")
        self.assertIsInstance(prov_groq, GroqProvider)

        # Custom OpenAI compatible protocol whitelisting works
        with patch("ai.providers.openai_provider.OpenAI") as mock_openai:
            prov = ProviderFactory.get_provider("custom_openai")
            self.assertIsInstance(prov, OpenAIProvider)

    @patch("ai.providers.openai_provider.OpenAI")
    def test_provider_connection_success(self, mock_openai):
        # 1. Mock OpenAI models.list call
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.models.list.return_value = MagicMock()

        # Call endpoint directly
        from admin.provider_management import test_provider
        user_mock = {"company_id": self.company_id}
        res = test_provider(self.prov_active_id, user=user_mock)
        
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["provider"], "Test Active Prov")
        self.assertIsNone(res["error"])
        mock_client.models.list.assert_called_once_with(timeout=5.0)

    @patch("ai.providers.openai_provider.OpenAI")
    def test_model_connection_success(self, mock_openai):
        # 2. Mock OpenAI completions call
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "pong-response"
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        # Call endpoint directly
        from admin.provider_management import test_model
        user_mock = {"company_id": self.company_id}
        res = test_model(self.model_a_id, user=user_mock)
        
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["model"], "model-active-a")
        self.assertEqual(res["response"], "pong-response")
        mock_client.chat.completions.create.assert_called_once_with(
            model="model-active-a",
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
            timeout=5.0
        )

    @patch("ai.providers.openai_provider.OpenAI")
    def test_provider_connection_invalid_credentials(self, mock_openai):
        # 3. Simulate Authentication Error
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        import openai
        # Mock models.list to raise AuthenticationError
        mock_client.models.list.side_effect = openai.AuthenticationError(
            message="Invalid API Key",
            response=MagicMock(),
            body=None
        )

        from admin.provider_management import test_provider
        user_mock = {"company_id": self.company_id}
        res = test_provider(self.prov_active_id, user=user_mock)
        
        self.assertEqual(res["status"], "failure")
        self.assertIn("Invalid API Key", res["error"])
        
        # Verify provider_health has status FAILED
        with engine.connect() as conn:
            health = conn.execute(
                text("SELECT status, last_error FROM provider_health WHERE provider_id = :p_id"),
                {"p_id": self.prov_active_id}
            ).fetchone()
        self.assertEqual(health.status, "FAILED")
        self.assertIn("Invalid API Key", health.last_error)

    @patch("ai.providers.openai_provider.OpenAI")
    def test_provider_connection_timeout(self, mock_openai):
        # 4. Simulate API Timeout
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        import openai
        mock_client.models.list.side_effect = openai.APITimeoutError("Request timed out")

        from admin.provider_management import test_provider
        user_mock = {"company_id": self.company_id}
        res = test_provider(self.prov_active_id, user=user_mock)
        
        self.assertEqual(res["status"], "failure")
        self.assertIn("Request timed out", res["error"])

    def test_test_inactive_model_rejected(self):
        # 5. Inactive model connection test rejected with 400
        from admin.provider_management import test_model
        user_mock = {"company_id": self.company_id}
        with self.assertRaises(HTTPException) as ctx:
            test_model(self.model_inactive_id, user=user_mock)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_test_endpoint_company_isolation(self):
        # 6. Provider connection test for other company's provider rejected with 403
        from admin.provider_management import test_provider
        other_user_mock = {"company_id": str(uuid.uuid4()).upper()}
        with self.assertRaises(HTTPException) as ctx:
            test_provider(self.prov_active_id, user=other_user_mock)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_update_provider_and_model_endpoints(self):
        from admin.provider_management import (
            test_provider, 
            update_provider, 
            UpdateProviderRequest,
            update_model,
            UpdateModelRequest
        )
        user_mock = {"company_id": self.company_id}
        
        # Test update provider details
        req_p = UpdateProviderRequest(provider_name="New Prov Name", provider_type="groq", base_url="https://new-api.org", is_active=True)
        res_p = update_provider(self.prov_active_id, req_p, user=user_mock)
        self.assertEqual(res_p["message"], "Provider updated")
        
        # Verify in DB
        with engine.connect() as conn:
            p_row = conn.execute(text("SELECT provider_name, base_url FROM llm_providers WHERE provider_id = :id"), {"id": self.prov_active_id}).fetchone()
        self.assertEqual(p_row.provider_name, "New Prov Name")
        self.assertEqual(p_row.base_url, "https://new-api.org")
        
        # Test update model details
        req_m = UpdateModelRequest(model_name="New Model Name", purpose="insight", is_active=True)
        res_m = update_model(self.model_a_id, req_m, user=user_mock)
        self.assertEqual(res_m["message"], "Model updated")
        
        # Verify in DB
        with engine.connect() as conn:
            m_row = conn.execute(text("SELECT model_name, purpose FROM llm_models WHERE model_id = :id"), {"id": self.model_a_id}).fetchone()
        self.assertEqual(m_row.model_name, "New Model Name")
        self.assertEqual(m_row.purpose, "insight")

    def test_save_api_key_endpoint(self):
        from admin.provider_management import save_provider_api_key, SaveApiKeyRequest
        from services.provider_credential_service import ProviderCredentialService
        user_mock = {"company_id": self.company_id}
        
        req = SaveApiKeyRequest(api_key="super-secret-key-123")
        res = save_provider_api_key(self.prov_active_id, req, user=user_mock)
        self.assertEqual(res["message"], "API key updated")
        
        # Verify encryption and decryption works
        decrypted = ProviderCredentialService.get_api_key(self.prov_active_id)
        self.assertEqual(decrypted, "super-secret-key-123")

    def test_fallback_management_endpoints(self):
        from admin.provider_management import (
            get_fallbacks, 
            add_fallback, 
            AddFallbackRequest,
            remove_fallback,
            reorder_fallbacks,
            ReorderFallbacksRequest
        )
        user_mock = {"company_id": self.company_id}
        
        # 1. Initially get_fallbacks should be empty for self.purpose
        fbs = get_fallbacks(user=user_mock)
        self.assertEqual(len([f for f in fbs if f["purpose"] == self.purpose]), 0)
        
        # 2. Add Model A as fallback
        req_add_a = AddFallbackRequest(purpose=self.purpose, model_id=self.model_a_id)
        res_add_a = add_fallback(req_add_a, user=user_mock)
        self.assertEqual(res_add_a["message"], "Fallback added")
        
        # 3. Add Model B as fallback
        req_add_b = AddFallbackRequest(purpose=self.purpose, model_id=self.model_b_id)
        res_add_b = add_fallback(req_add_b, user=user_mock)
        self.assertEqual(res_add_b["message"], "Fallback added")
        
        # 4. Get fallbacks and check ordering
        fbs = get_fallbacks(user=user_mock)
        purpose_fbs = [f for f in fbs if f["purpose"] == self.purpose]
        self.assertEqual(len(purpose_fbs), 2)
        self.assertEqual(purpose_fbs[0]["model_id"], self.model_a_id)
        self.assertEqual(purpose_fbs[0]["priority_order"], 1)
        self.assertEqual(purpose_fbs[1]["model_id"], self.model_b_id)
        self.assertEqual(purpose_fbs[1]["priority_order"], 2)
        
        # 5. Reorder them (B first, A second)
        req_reorder = ReorderFallbacksRequest(
            purpose=self.purpose, 
            ordered_fallback_ids=[purpose_fbs[1]["fallback_id"], purpose_fbs[0]["fallback_id"]]
        )
        res_reorder = reorder_fallbacks(req_reorder, user=user_mock)
        self.assertEqual(res_reorder["message"], "Fallbacks reordered")
        
        # Verify new order
        fbs = get_fallbacks(user=user_mock)
        purpose_fbs = [f for f in fbs if f["purpose"] == self.purpose]
        self.assertEqual(purpose_fbs[0]["model_id"], self.model_b_id)
        self.assertEqual(purpose_fbs[0]["priority_order"], 1)
        self.assertEqual(purpose_fbs[1]["model_id"], self.model_a_id)
        self.assertEqual(purpose_fbs[1]["priority_order"], 2)
        
        # 6. Remove fallback B
        res_remove = remove_fallback(purpose_fbs[0]["fallback_id"], user=user_mock)
        self.assertEqual(res_remove["message"], "Fallback removed")
        
        # Verify Model A is shifted to priority 1
        fbs = get_fallbacks(user=user_mock)
        purpose_fbs = [f for f in fbs if f["purpose"] == self.purpose]
        self.assertEqual(len(purpose_fbs), 1)
        self.assertEqual(purpose_fbs[0]["model_id"], self.model_a_id)
        self.assertEqual(purpose_fbs[0]["priority_order"], 1)

if __name__ == "__main__":
    unittest.main()
