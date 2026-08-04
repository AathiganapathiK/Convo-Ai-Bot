from sqlglot import exp

from ai.ast import SchemaValidationError, ValidationErrorCode
from .base import BaseRepairStrategy
from .models import RepairContext, RepairCandidate
from .result import RepairResult
from .similarity import find_best_match


class TableRepair(BaseRepairStrategy):
    """
    Strategy to identify and fix invalid table names in SQL queries.
    E.g., "SELECT Sales FROM Sale" -> "SELECT Sales FROM Sales"
    """

    priority = 20

    def can_repair(self, context: RepairContext) -> bool:
        for err in context.validation_errors:
            if isinstance(err, SchemaValidationError):
                if err.code == ValidationErrorCode.TABLE_NOT_FOUND:
                    return True
        return False

    def repair(self, context: RepairContext) -> RepairResult:
        schema_keys = list(context.schema_metadata.keys())

        for err in context.validation_errors:
            if not isinstance(err, SchemaValidationError):
                continue
            if err.code != ValidationErrorCode.TABLE_NOT_FOUND:
                continue

            invalid_table = err.table
            if not invalid_table:
                continue

            # Build candidates based on whether invalid_table specifies schema
            if "." in invalid_table:
                candidates = schema_keys
            else:
                candidates = [k.split(".")[-1] for k in schema_keys]

            if not candidates:
                continue

            best = find_best_match(invalid_table, candidates)
            if not best:
                continue

            replacement, confidence = best

            # Resolve the full table key from the chosen replacement
            if "." in invalid_table:
                full_name = replacement
            else:
                full_name = None
                for key in schema_keys:
                    if key.split(".")[-1].lower() == replacement.lower():
                        full_name = key
                        break
                if not full_name:
                    full_name = replacement

            # Split into db (schema) and table (base name)
            if "." in full_name:
                db, table = full_name.split(".", 1)
            else:
                db, table = None, full_name

            candidate = RepairCandidate(
                original=invalid_table,
                replacement=full_name,
                confidence=confidence,
                reason=f"Repaired table '{invalid_table}' to '{full_name}' via similarity match.",
            )

            # Traverse AST to replace matched table nodes
            modified = False
            if context.ast is None:
                raise ValueError("AST is missing.")
            for table_node in context.ast.find_all(exp.Table):
                # Check for match
                is_match = False
                if "." in invalid_table:
                    import re
                    cleaned_node = re.sub(r'["`\[\]]', "", table_node.sql().lower())
                    cleaned_invalid = re.sub(r'["`\[\]]', "", invalid_table.lower())
                    is_match = (cleaned_node == cleaned_invalid)
                else:
                    is_match = (table_node.name.lower() == invalid_table.lower())

                if is_match:
                    table_node.set("this", exp.to_identifier(table))
                    if db:
                        table_node.set("db", exp.to_identifier(db))
                    modified = True
            if context.ast is None:
                raise ValueError("AST is missing.")
                
            if modified:
                repaired_sql = context.ast.sql()
                context.current_sql = repaired_sql
                context.applied_repairs.append(candidate)
                return RepairResult(
                    success=True,
                    repaired=True,
                    repaired_sql=repaired_sql,
                    repair_type="TABLE",
                    candidate=candidate,
                )

        return RepairResult(
            success=False,
            repaired=False,
            repaired_sql=context.current_sql,
            repair_type="TABLE",
            errors=["No valid repair candidate found for invalid tables."],
        )
