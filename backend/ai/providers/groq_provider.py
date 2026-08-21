import os

import core.config
from services.provider_credential_service import (
    ProviderCredentialService
)

import logging
logger = logging.getLogger(__name__)

from groq import Groq



from ai.providers.base_provider import (
    BaseProvider
)



class GroqProvider(
    BaseProvider
):

    def __init__(self, company_id=None):

        api_key = (
            ProviderCredentialService
            .get_provider_key_by_type(
                "groq",
                company_id=company_id
            )
        )
        source = "database"

        if api_key:
            logger.info("Groq API key loaded from database.")
        else:
            logger.warning("Using fallback .env Groq key.")
            source = "env"

            api_key = os.getenv(
                "GROQ_API_KEY"
            )

        self.client = Groq(
            api_key=api_key
        )

    def chat_completion(
        self,
        model: str,
        messages: list,
        temperature: float = 0,
        timeout: float = 10.0
    ):


        return (
            self.client
            .chat
            .completions
            .create(
                model=model,
                messages=messages,
                temperature=temperature,
                timeout=timeout
            )
        )