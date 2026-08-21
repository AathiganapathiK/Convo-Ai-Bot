import os
import core.config
from ai.providers.provider_factory import ProviderFactory

def generate_general_response(
    question: str
) -> str:

    prompt = f"""
You are a friendly Enterprise Analytics Assistant.

Rules:
- Reply naturally.
- Maximum 50 words.
- Do not generate SQL.
- Do not mention databases.
- Be conversational.

User:
{question}
"""

    provider_type = os.getenv("DEFAULT_PROVIDER", "groq")
    model_name = os.getenv("DEFAULT_MODEL", "qwen2.5:7b")
    
    provider = ProviderFactory.get_provider(provider_type)
    response = provider.chat_completion(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.5
    )
    
    content = ""
    if response and getattr(response, "choices", None):
        choice = response.choices[0]
        if choice and getattr(choice, "message", None):
            message = choice.message
            if message and getattr(message, "content", None) is not None:
                val = message.content
                if val is not None:
                    content = val.strip()
                    
    return content