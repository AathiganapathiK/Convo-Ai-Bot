from ai.providers.groq_provider import (
    GroqProvider
)


class ProviderFactory:

    @staticmethod
    def get_provider(
        provider_type: str,
        company_id = None
    ):

        provider_type = (
            provider_type.lower()
        )

        if provider_type == "groq":

            return GroqProvider(company_id=company_id)

        raise ValueError(
            f"Unsupported provider: "
            f"{provider_type}"
        )