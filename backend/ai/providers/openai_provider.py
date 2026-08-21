import os
import logging
from openai import OpenAI
from sqlalchemy import text
from database import engine
from services.encryption_service import EncryptionService
from ai.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """
    Generic provider utilizing the OpenAI SDK.
    Compatible with OpenAI, Nvidia API, OpenRouter, and any other OpenAI-compatible gateway.
    """
    def __init__(self, provider_type: str = "openai", company_id=None):
        self.provider_type = provider_type.lower()
        
        # 1. Attempt to fetch base_url and encrypted_api_key from DB
        base_url = None
        api_key = None
        
        try:
            conditions = ["provider_type = :provider_type", "is_active = 1"]
            params = {"provider_type": self.provider_type}
            if company_id:
                conditions.append("company_id = :company_id")
                params["company_id"] = company_id

            query = f"""
            SELECT TOP 1
                base_url,
                encrypted_api_key
            FROM llm_providers
            WHERE
                {" AND ".join(conditions)}
            """
            with engine.connect() as connection:
                row = connection.execute(text(query), params).fetchone()
                if row:
                    base_url = row.base_url
                    if row.encrypted_api_key:
                        api_key = EncryptionService.decrypt(row.encrypted_api_key)
        except Exception as e:
            logger.warning(f"Failed to load provider credentials for {self.provider_type} from database: {e}")

        # 2. Fall back to environment variables if not found in database
        env_prefix = self.provider_type.upper()
        if not api_key:
            api_key = os.getenv(f"{env_prefix}_API_KEY")
        
        if not base_url:
            base_url = os.getenv(f"{env_prefix}_BASE_URL")
        
        # Standard defaults for base URL of standard providers
        if not base_url:
            if self.provider_type == "openai":
                base_url = "https://api.openai.com/v1"
            elif self.provider_type == "nvidia":
                base_url = "https://integrate.api.nvidia.com/v1"
            else:
                base_url = "https://api.openai.com/v1"

        if not api_key:
            logger.warning(f"No API key resolved for {self.provider_type}. Please configure it in the database or set the {env_prefix}_API_KEY environment variable.")

        logger.info(f"OpenAI-compatible provider '{self.provider_type}' initialized pointing to base_url: {base_url}")
        
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )

    def chat_completion(
        self,
        model: str,
        messages: list,
        temperature: float = 0,
        timeout: float = 10.0
    ):
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            timeout=timeout
        )
