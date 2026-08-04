from sqlglot import exp
from typing import Dict

from ai.ast import SchemaValidationError, ValidationErrorCode
from .base import BaseRepairStrategy
from .models import RepairContext, RepairCandidate
from .result import RepairResult
from .similarity import find_best_match


class ColumnRepair(BaseRepairStrategy):
    """
    Strategy to identify and fix invalid column names in SQL queries.
    E.g., "SELECT Sale FROM Sales" -> "SELECT Sales FROM Sales"
    """

    priority = 10

    def can_repair(self, context: RepairContext) -> bool:
        for err in context.validation_errors:
            if isinstance(err, SchemaValidationError):
                if err.code in (ValidationErrorCode.COLUMN_NOT_FOUND, ValidationErrorCode.COLUMN_NOT_RESOLVED):
                    return True
        return False

    def repair(self, context: RepairContext) -> RepairResult:
        alias_map = self._build_alias_map(context)

        for err in context.validation_errors:
            if not isinstance(err, SchemaValidationError):
                continue
            if err.code not in (ValidationErrorCode.COLUMN_NOT_FOUND, ValidationErrorCode.COLUMN_NOT_RESOLVED):
                continue

            invalid_col = err.column
            target_table = err.table

            if not invalid_col:
                continue

            # Gather candidate column names from referenced tables
            candidates = []
            if target_table:
                resolved_table = self._resolve_table_name(target_table, context.schema_metadata)
                if resolved_table in context.schema_metadata:
                    candidates = list(context.schema_metadata[resolved_table].get("columns", []))
            else:
                for t in context.metadata.tables:
                    resolved = self._resolve_table_name(t.name, context.schema_metadata)
                    if resolved in context.schema_metadata:
                        candidates.extend(context.schema_metadata[resolved].get("columns", []))
                for j in context.metadata.joins:
                    resolved = self._resolve_table_name(j.table, context.schema_metadata)
                    if resolved in context.schema_metadata:
                        candidates.extend(context.schema_metadata[resolved].get("columns", []))
                candidates = list(set(candidates))

            if not candidates:
                continue

            best = find_best_match(invalid_col, candidates)
            if not best:
                continue

            replacement, confidence = best
            candidate = RepairCandidate(
                original=invalid_col,
                replacement=replacement,
                confidence=confidence,
                reason=f"Repaired column '{invalid_col}' to '{replacement}' via similarity scoring.",
            )

            # Traverse AST to replace matched column nodes
            modified = False
            if context.ast is None:
                raise ValueError("AST is missing.")
            for col_node in context.ast.find_all(exp.Column):
                if col_node.name.lower() == invalid_col.lower():
                    if self._matches_table(col_node, target_table, context, alias_map):
                        col_node.set("this", exp.to_identifier(replacement))
                        modified = True

            if modified:
                repaired_sql = context.ast.sql()
                context.current_sql = repaired_sql
                context.applied_repairs.append(candidate)
                return RepairResult(
                    success=True,
                    repaired=True,
                    repaired_sql=repaired_sql,
                    repair_type="COLUMN",
                    candidate=candidate,
                )

        return RepairResult(
            success=False,
            repaired=False,
            repaired_sql=context.current_sql,
            repair_type="COLUMN",
            errors=["No valid repair candidate found for invalid columns."],
        )

    def _matches_table(
        self,
        col_node: exp.Column,
        target_table: str | None,
        context: RepairContext,
        alias_map: Dict[str, str],
    ) -> bool:
        if not target_table:
            return True
        col_table = col_node.text("table")
        if not col_table:
            # Unqualified column. Since we have a single table context or it's mapped, assume match.
            return True

        resolved = alias_map.get(col_table.upper(), col_table)
        resolved_full = self._resolve_table_name(resolved, context.schema_metadata)
        target_full = self._resolve_table_name(target_table, context.schema_metadata)
        return resolved_full == target_full
