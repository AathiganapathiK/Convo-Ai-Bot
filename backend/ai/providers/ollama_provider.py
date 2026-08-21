import os
import requests
import json
import logging
from ai.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)

class OllamaProvider(BaseProvider):
    def __init__(self, company_id=None):
        # Default Ollama host is http://localhost:11434
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        logger.info(f"Ollama provider initialized pointing to {self.host}")

    def chat_completion(self, model: str, messages: list, temperature: float = 0, timeout: float = 10.0) -> None:
        url = f"{self.host}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        
        # Extract response content and structure as OpenAI ChatCompletion structure
        data = response.json()
        
        class ChoiceMessage:
            def __init__(self, content):
                self.content = content

        class Choice:
            def __init__(self, message):
                self.message = message

        class ChatCompletionResponse:
            def __init__(self, content):
                self.choices = [Choice(ChoiceMessage(content))]
                self.usage = None

        choices = data.get("choices", [])
        content = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            
        return ChatCompletionResponse(content)
