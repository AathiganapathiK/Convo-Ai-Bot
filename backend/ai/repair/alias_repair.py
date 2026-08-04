from sqlglot import exp

from ai.ast import SchemaValidationError, ValidationErrorCode
from .base import BaseRepairStrategy
from .models import RepairContext, RepairCandidate
from .result import RepairResult
from .similarity import find_best_match


class AliasRepair(BaseRepairStrategy):
    """
    Strategy to identify and fix invalid column table prefixes or aliases.
    E.g., "SELECT X.Sales FROM Sales S" -> "SELECT S.Sales FROM Sales S"
    """

    priority = 30

    def can_repair(self, context: RepairContext) -> bool:
        for err in context.validation_errors:
            if isinstance(err, SchemaValidationError):
                if err.code == ValidationErrorCode.ALIAS_NOT_FOUND:
                    return True
        return False

    def repair(self, context: RepairContext) -> RepairResult:
        for err in context.validation_errors:
            if not isinstance(err, SchemaValidationError):
                continue
            if err.code != ValidationErrorCode.ALIAS_NOT_FOUND:
                continue

            invalid_alias = err.table
            if not invalid_alias:
                continue

            # Build candidates for correct active aliases / table names
            candidates = []
            for table in context.metadata.tables:
                if table.alias:
                    candidates.append(table.alias)
                else:
                    candidates.append(table.name.split(".")[-1])
            for join in context.metadata.joins:
                if join.alias:
                    candidates.append(join.alias)
                else:
                    candidates.append(join.table.split(".")[-1])
            for cte in context.metadata.ctes:
                candidates.append(cte)

            candidates = list(set(candidates))

            if len(candidates) == 1:
                replacement, confidence = candidates[0], 1.0
            else:
                best = find_best_match(invalid_alias, candidates)
                if not best:
                    continue
                replacement, confidence = best

            candidate = RepairCandidate(
                original=invalid_alias,
                replacement=replacement,
                confidence=confidence,
                reason=f"Repaired alias '{invalid_alias}' to '{replacement}' via similarity matching.",
            )

            if context.ast is None:
                raise ValueError("AST is missing.")

            # Traverse AST and update prefix of matched Column nodes
            modified = False
            for col_node in context.ast.find_all(exp.Column):
                col_table = col_node.text("table")
                if col_table and col_table.lower() == invalid_alias.lower():
                    col_node.set("table", exp.to_identifier(replacement))
                    modified = True

            if modified:
                repaired_sql = context.ast.sql()
                context.current_sql = repaired_sql
                context.applied_repairs.append(candidate)
                return RepairResult(
                    success=True,
                    repaired=True,
                    repaired_sql=repaired_sql,
                    repair_type="ALIAS",
                    candidate=candidate,
                )

        return RepairResult(
            success=False,
            repaired=False,
            repaired_sql=context.current_sql,
            repair_type="ALIAS",
            errors=["No valid repair candidate found for invalid aliases."],
        )
