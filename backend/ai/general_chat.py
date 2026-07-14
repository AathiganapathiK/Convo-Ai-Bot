from groq import Groq
import os
from dotenv import load_dotenv

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if not os.getenv("APP_ENV"):
    load_dotenv(BASE_DIR / ".env")

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

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

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.5,
        max_tokens=60,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
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