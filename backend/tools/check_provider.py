from ai.providers.provider_factory import (
    ProviderFactory
)

provider = (
    ProviderFactory.get_provider(
        "groq"
    )
)

print(type(provider))