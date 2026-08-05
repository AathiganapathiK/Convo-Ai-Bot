from semantic.semantic_resolver import SemanticResolver


class FollowupValidator:

    @staticmethod
    def validate(
        questions,
        original_question,
        connection_id
    ):
        """
        Validate generated follow-up questions using the existing
        Semantic Resolver.

        Returns only questions that pass semantic retrieval.
        """

        print("Entered: validate")
        print(f"connection_id = {connection_id}")
        valid_questions = []

        print("\n========== FOLLOWUP VALIDATION ==========")

        for followup_question in questions:
            try:
                print(f"\nFollow-up: {followup_question}")
                print(f"Original Question: {original_question}")
                print(f"Validating Follow-up: {followup_question}")

                semantic_result = SemanticResolver.resolve(
                        connection_id,
                        followup_question
                    )
                
                print("\n========== SEMANTIC RESULT ==========")
                print(semantic_result)

                retrieval = (
                    semantic_result.get("retrieval", {})
                    if semantic_result
                    else {}
                )

                status = retrieval.get("status")

                print(f"Status: {status}")

                if status == "COMPLETE":
                    valid_questions.append(followup_question)

            except Exception as ex:
                print(
                    f"[FollowupValidator] Failed validation: {followup_question}"
                )
                print(ex)

        return valid_questions