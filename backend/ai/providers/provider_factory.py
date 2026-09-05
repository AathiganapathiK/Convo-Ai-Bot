from ai.providers.groq_provider import (
    GroqProvider
)


class ProviderFactory:

    @staticmethod
    def get_provider(
        provider_type: str,
        company_id = None,
        provider_id = None
    ):
        """
        Build a provider client for one CONFIGURED provider row.

        `provider_id` matters when a company has several rows of the same
        type. Resolving the credential by type alone made every Groq route
        share one key, so three separately-registered Groq accounts drew on a
        single daily quota and failover between them changed nothing. Passing
        the id lets each row use its own key; omitting it keeps the old
        by-type behaviour for callers that have no id to give.
        """

        provider_type = (
            provider_type.lower()
        )

        if provider_type == "groq":

            return GroqProvider(company_id=company_id, provider_id=provider_id)

        if provider_type == "ollama":
            from ai.providers.ollama_provider import OllamaProvider
            return OllamaProvider(company_id=company_id)

        # Explicitly supported OpenAI-compatible provider types
        openai_compatible_types = {"openai", "nvidia", "openrouter", "custom_openai"}

        if provider_type in openai_compatible_types:
            try:
                from ai.providers.openai_provider import OpenAIProvider
                return OpenAIProvider(provider_type=provider_type, company_id=company_id)
            except Exception as e:
                raise ValueError(
                    f"Failed to initialize OpenAI-compatible provider '{provider_type}': {e}"
                )

        raise ValueError(
            f"Unsupported provider type: '{provider_type}'"
        )