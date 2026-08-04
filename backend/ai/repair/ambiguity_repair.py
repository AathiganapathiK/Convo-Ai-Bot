from sqlglot import exp
from typing import List, Optional

from ai.ast import SchemaValidationError, ValidationErrorCode
from .base import BaseRepairStrategy
from .models import RepairContext, RepairCandidate
from .result import RepairResult


class AmbiguityRepair(BaseRepairStrategy):
    """
    Strategy to resolve ambiguous column references by qualifying them with an appropriate table alias.
    E.g., "SELECT ProductKey FROM Sales S JOIN Products P..." -> "SELECT S.ProductKey FROM..."
    """

    priority = 40

    def can_repair(self, context: RepairContext) -> bool:
        for err in context.validation_errors:
            if isinstance(err, SchemaValidationError):
                if err.code == ValidationErrorCode.COLUMN_AMBIGUOUS:
                    return True
        return False

    def repair(self, context: RepairContext) -> RepairResult:
        for err in context.validation_errors:
            if not isinstance(err, SchemaValidationError):
                continue
            if err.code != ValidationErrorCode.COLUMN_AMBIGUOUS:
                continue

            ambiguous_col = err.column
            matching_tables = err.possible_tables

            if not ambiguous_col or not matching_tables:
                continue

            # Pick the best qualifying prefix using query context (prefer FROM tables over JOINs)
            prefix = self._choose_prefix(matching_tables, context)
            if not prefix:
                continue

            candidate = RepairCandidate(
                original=ambiguous_col,
                replacement=f"{prefix}.{ambiguous_col}",
                confidence=1.0,
                reason=f"Qualified ambiguous column '{ambiguous_col}' with table/alias prefix '{prefix}'.",
            )

            # Traverse AST to find and qualify the unqualified column
            modified = False
            if context.ast is None:
                raise ValueError("AST is missing.")
            for col_node in context.ast.find_all(exp.Column):
                if col_node.name.lower() == ambiguous_col.lower() and not col_node.text("table"):
                    col_node.set("table", exp.to_identifier(prefix))
                    modified = True

            if modified:
                repaired_sql = context.ast.sql()
                context.current_sql = repaired_sql
                context.applied_repairs.append(candidate)
                return RepairResult(
                    success=True,
                    repaired=True,
                    repaired_sql=repaired_sql,
                    repair_type="AMBIGUITY",
                    candidate=candidate,
                )

        return RepairResult(
            success=False,
            repaired=False,
            repaired_sql=context.current_sql,
            repair_type="AMBIGUITY",
            errors=["No valid repair candidate found for ambiguous columns."],
        )

    def _choose_prefix(self, matching_tables: List[str], context: RepairContext) -> Optional[str]:
        # 1. Prefer the primary table in FROM clause
        for table_name in matching_tables:
            resolved_target = self._resolve_table_name(table_name, context.schema_metadata)
            if not resolved_target:
                continue
            for t in context.metadata.tables:
                resolved = self._resolve_table_name(t.name, context.schema_metadata)
                if resolved == resolved_target:
                    return t.alias if t.alias else t.name.split(".")[-1]

        # 2. Fall back to joined tables
        for table_name in matching_tables:
            resolved_target = self._resolve_table_name(table_name, context.schema_metadata)
            if not resolved_target:
                continue
            for j in context.metadata.joins:
                resolved = self._resolve_table_name(j.table, context.schema_metadata)
                if resolved == resolved_target:
                    return j.alias if j.alias else j.table.split(".")[-1]

        return None
