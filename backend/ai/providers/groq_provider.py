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

    def __init__(self, company_id=None, provider_id=None):

        # This provider row's own credential first.
        #
        # Several Groq rows can be registered for one company, each a separate
        # account with its own daily quota. Resolving by type alone gave them
        # all the same key, so routing from one to the next on a rate limit
        # was routing to the same account. The by-type lookup remains as the
        # fallback for callers with no provider_id.
        api_key = None
        source = "database"

        if provider_id:
            try:
                api_key = ProviderCredentialService.get_api_key(provider_id)
            except Exception as exc:
                logger.warning(
                    "Could not read the credential for provider %s (%s); "
                    "falling back to the provider-type lookup.",
                    provider_id, str(exc).splitlines()[0][:120],
                )

            if api_key:
                logger.info("Groq API key loaded for provider %s.", provider_id)

        if not api_key:
            api_key = (
                ProviderCredentialService
                .get_provider_key_by_type(
                    "groq",
                    company_id=company_id
                )
            )
            if api_key:
                logger.info("Groq API key loaded from database (by type).")

        if not api_key:
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