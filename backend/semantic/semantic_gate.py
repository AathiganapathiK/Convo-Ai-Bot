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

        # Check ambiguity result if available. If strong ambiguity is present, block SQL generation.
        ambig_res = semantic_result.get("ambiguity_result")
        if ambig_res:
            from semantic.matching.models import ResolutionStatus
            if ambig_res.status == ResolutionStatus.STRONG_AMBIGUITY:
                return {
                    "allowed": False,
                    "status": "STRONG_AMBIGUITY",
                    "confidence": confidence,
                    "reason": "Strong ambiguity detected between candidates. Clarification is required."
                }
            elif ambig_res.status == ResolutionStatus.PARTIAL_MATCH:
                return {
                    "allowed": False,
                    "status": "PARTIAL_MATCH",
                    "confidence": confidence,
                    "reason": "Partial semantic coverage requires clarification."
                }



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