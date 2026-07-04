import json

from services.llm_execution_service import (
LLMExecutionService
)

from ai.insights.followup_templates import (
FOLLOWUP_TEMPLATE
)

class FollowupGenerator:

    @staticmethod
    def generate(
        question,
        serialized_data,
        company_id=None
    ):

        prompt = f"""

    Original Question:
    {question}

    Query Result:
    {serialized_data}

    {FOLLOWUP_TEMPLATE}
    """

        response = (
            LLMExecutionService.execute(
                purpose="insight",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                company_id=company_id
            )
        )

        if not response or not getattr(response, "choices", None):
            return []
        
        choice = response.choices[0]
        if not choice or not getattr(choice, "message", None):
            return []
            
        message = choice.message
        if not message or getattr(message, "content", None) is None:
            return []

        content = message.content

        if content is None:
            return []

        content = content.strip()

        try:
            if "```" in content:
                first_ticks = content.find("```")
                first_newline = content.find("\n", first_ticks)
                if first_newline != -1:
                    code_start = first_newline + 1
                else:
                    code_start = first_ticks + 3
                
                last_ticks = content.rfind("```")
                if last_ticks > code_start:
                    content = content[code_start:last_ticks].strip()
                else:
                    content = content[code_start:].strip()
            else:
                content = content.strip()

            questions = json.loads(content)

            if not isinstance(questions, list):
                questions = []

        except Exception:
            questions = []



        return questions
