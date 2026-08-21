import unittest
from unittest.mock import patch, MagicMock
import os

from ai.providers.provider_factory import ProviderFactory
from ai.providers.openai_provider import OpenAIProvider

class TestOpenAIProvider(unittest.TestCase):

    @patch("ai.providers.openai_provider.OpenAI")
    @patch("ai.providers.openai_provider.engine.connect")
    def test_provider_initialization_defaults(self, mock_connect, mock_openai_class):
        # Setup mock db query return None (simulate no entry in DB)
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None

        # Test OpenAI default URL
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-openai"}):
            provider = ProviderFactory.get_provider("openai")
            self.assertIsInstance(provider, OpenAIProvider)
            mock_openai_class.assert_called_with(
                base_url="https://api.openai.com/v1",
                api_key="test-key-openai"
            )

    @patch("ai.providers.openai_provider.OpenAI")
    @patch("ai.providers.openai_provider.engine.connect")
    def test_provider_initialization_nvidia_defaults(self, mock_connect, mock_openai_class):
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None

        # Test Nvidia default URL
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key-nvidia"}):
            provider = ProviderFactory.get_provider("nvidia")
            self.assertIsInstance(provider, OpenAIProvider)
            mock_openai_class.assert_called_with(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key="test-key-nvidia"
            )

    @patch("ai.providers.openai_provider.OpenAI")
    @patch("ai.providers.openai_provider.engine.connect")
    def test_provider_initialization_from_db(self, mock_connect, mock_openai_class):
        # Setup mock db query to return base_url and encrypted key
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        mock_row = MagicMock()
        mock_row.base_url = "https://custom-gateway.v1"
        mock_row.encrypted_api_key = b"encrypted-data"
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        with patch("services.encryption_service.EncryptionService.decrypt", return_value="decrypted-key"):
            provider = ProviderFactory.get_provider("custom_openai")
            self.assertIsInstance(provider, OpenAIProvider)
            mock_openai_class.assert_called_with(
                base_url="https://custom-gateway.v1",
                api_key="decrypted-key"
            )

    @patch("ai.providers.openai_provider.OpenAI")
    @patch("ai.providers.openai_provider.engine.connect")
    def test_chat_completion_proxy(self, mock_connect, mock_openai_class):
        # Verify provider delegates chat completion calls to the OpenAI client
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key-nvidia"}):
            provider = ProviderFactory.get_provider("nvidia")
            provider.chat_completion(
                model="meta/llama-3.3-70b-instruct",
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.2
            )
            mock_client.chat.completions.create.assert_called_once_with(
                model="meta/llama-3.3-70b-instruct",
                messages=[{"role": "user", "content": "hi"}],
                temperature=0.2,
                timeout=10.0
            )

if __name__ == "__main__":
    unittest.main()
