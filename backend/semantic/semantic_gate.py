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
            elif ambig_res.status == ResolutionStatus.WEAK_AMBIGUITY:
                # Gate 3 Step 21c. WEAK_AMBIGUITY carries a dominant candidate,
                # so it was never checked here before - it fell straight
                # through to the count-based retrieval_status below and was
                # silently allowed, regardless of how many genuine
                # alternatives the resolver had retained alongside the
                # dominant one.
                #
                # value_matches (not ambig_res.candidates) is the count that
                # matters: candidates is the raw, unfiltered list the
                # classifier considered, which can still include an accidental
                # match ("city" fuzzy-matching ELECTRONIC CITY) that the
                # candidate-retention step already discarded. value_matches is
                # what survived that filtering - only genuine alternatives
                # (same column, sharing a matched token with the dominant
                # candidate) remain in it. A WEAK_AMBIGUITY case that filtered
                # down to exactly one value has nothing left to ask about, so
                # it is left exactly as before: allowed to fall through.
                value_matches = semantic_result.get("value_matches") or []
                if len(value_matches) > 1:
                    return {
                        "allowed": False,
                        "status": "WEAK_AMBIGUITY",
                        "confidence": confidence,
                        "reason": "Multiple genuine candidate values remain. Clarification is required."
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