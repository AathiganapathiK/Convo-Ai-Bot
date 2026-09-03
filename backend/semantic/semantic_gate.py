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

        # Check cross-table reachability between filter/dimension tables and metric tables
        connection_id = (
            semantic_result.get("connection_id")
            or (semantic_result.get("retrieval") or {}).get("connection_id")
        )
        if not connection_id:
            for key in ("metric_objects", "dimension_objects", "value_matches"):
                objs = semantic_result.get(key) or []
                if isinstance(objs, list):
                    for obj in objs:
                        if isinstance(obj, dict) and obj.get("connection_id"):
                            connection_id = str(obj["connection_id"])
                            break
                if connection_id:
                    break

        if connection_id:
            metric_objs = semantic_result.get("metric_objects") or []
            dimension_objs = semantic_result.get("dimension_objects") or []
            value_matches = semantic_result.get("value_matches") or []

            metric_tables = set()
            for m in metric_objs:
                if isinstance(m, dict) and m.get("table_name"):
                    tname = str(m["table_name"]).strip()
                    if tname:
                        metric_tables.add(tname)

            filter_items = []
            for obj in value_matches + dimension_objs:
                if isinstance(obj, dict) and obj.get("table_name"):
                    tname = str(obj["table_name"]).strip()
                    cname = (
                        obj.get("business_name")
                        or obj.get("dimension_name")
                        or obj.get("column_name")
                        or "dimension"
                    )
                    if tname:
                        filter_items.append((tname, cname))

            if metric_tables and filter_items:
                try:
                    from semantic.relationship_expander import RelationshipExpander
                    from collections import defaultdict, deque
                    graph = RelationshipExpander.build_graph(connection_id)

                    ci_graph = defaultdict(set)
                    for src, targets in graph.items():
                        src_u = src.strip().upper()
                        for tgt in targets:
                            ci_graph[src_u].add(tgt.strip().upper())

                    for m_table in metric_tables:
                        m_u = m_table.strip().upper()
                        for f_table, c_name in filter_items:
                            f_u = f_table.strip().upper()
                            if f_u == m_u:
                                continue

                            connected = False
                            if f_u in ci_graph.get(m_u, set()):
                                connected = True
                            else:
                                queue = deque([f_u])
                                visited = {f_u}
                                while queue:
                                    curr = queue.popleft()
                                    if curr == m_u:
                                        connected = True
                                        break
                                    for nxt in ci_graph.get(curr, set()):
                                        if nxt not in visited:
                                            visited.add(nxt)
                                            queue.append(nxt)

                            if not connected:
                                return {
                                    "allowed": False,
                                    "status": "UNSUPPORTED_CROSS_TABLE",
                                    "confidence": confidence,
                                    "reason": (
                                        f"Requested dimension/filter '{c_name}' on table '{f_table}' "
                                        f"has no verified schema relationship with metric table '{m_table}'."
                                    )
                                }
                except Exception:
                    pass

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