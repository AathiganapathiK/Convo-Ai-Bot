from admin import connection_management
import json

from services.llm_execution_service import (
LLMExecutionService
)
from ai.insights.followup_validator import FollowupValidator

from ai.insights.followup_templates import (
FOLLOWUP_TEMPLATE
)
from core.logger import debug_print as print

class FollowupGenerator:

    @staticmethod
    def generate(
        question: str,
        serialized_data: str,
        semantic_result,
        runtime_context,
        history=None,
        company_id=None,
        connection_id=None
    ):

        prompt = f"""
ORIGINAL QUESTION
{question}

CONVERSATION HISTORY
{history or "None"}

SEMANTIC RUNTIME
{runtime_context}

RESOLVED METRICS
{semantic_result.get("metrics", [])}

RESOLVED DIMENSIONS
{semantic_result.get("dimensions", [])}

MATCHED DIMENSION VALUES
{semantic_result.get("value_matches", [])}

CURRENT QUERY RESULT
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

        validated_questions = FollowupValidator.validate(
            questions=questions,
            original_question=question,
            connection_id=connection_id
        )

        print("\n========== FOLLOWUPS ==========")
        print(f"Generated: {len(questions)}")
        print(f"Validated: {len(validated_questions)}")
        print(f"Rejected: {len(questions) - len(validated_questions)}")
        print("================================")

        return validated_questions  
