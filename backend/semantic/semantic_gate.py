# Purpose
# The Semantic Gate decides:
# "Do we have enough semantic understanding to continue generating SQL?"

class SemanticGate:
    """
    Enterprise Semantic Retrieval Gate.

    Decides whether the retrieval pipeline has produced
    sufficient semantic grounding to continue with SQL generation.
    """

    @staticmethod
    def evaluate(semantic_result):

        retrieval = semantic_result.get("retrieval", {})

        status = retrieval.get("status", "INSUFFICIENT")
        confidence = retrieval.get("confidence", 0.0)
        resolved_components = retrieval.get("resolved_components", 0)

        # --------------------------------------------------
        # COMPLETE
        # --------------------------------------------------

        if status == "COMPLETE":

            return {
                "allowed": True,
                "status": status,
                "confidence": confidence,
                "reason": None
            }

        # --------------------------------------------------
        # PARTIAL
        # --------------------------------------------------

        if status == "PARTIAL":

            return {
                "allowed": True,
                "status": status,
                "confidence": confidence,
                "reason": (
                    "Partial semantic context resolved."
                )
            }

        # --------------------------------------------------
        # INSUFFICIENT
        # --------------------------------------------------

        return {
            "allowed": False,
            "status": "INSUFFICIENT",
            "confidence": confidence,
            "reason": (
                "Unable to confidently resolve the business terms "
                "in the question."
            )
        }