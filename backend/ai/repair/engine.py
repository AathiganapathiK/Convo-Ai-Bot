import time
from typing import Dict

from ai.validation_pipeline import ValidationPipeline, ValidationPipelineResult
from .models import RepairContext
from .result import RepairResult, RepairStatus
from .column_repair import ColumnRepair
from .table_repair import TableRepair
from .alias_repair import AliasRepair
from .ambiguity_repair import AmbiguityRepair


class RepairEngine:
    """
    Orchestrates the SQL repair pipeline using an injected ValidationPipeline.
    Maintains a loop of validation -> repair strategy selection -> AST modification -> re-validation.
    """

    def __init__(self, pipeline: ValidationPipeline):
        self.pipeline = pipeline
        self.strategies = sorted(
            [
                ColumnRepair(),
                TableRepair(),
                AliasRepair(),
                AmbiguityRepair(),
            ],
            key=lambda strategy: strategy.priority,
        )

    def repair_query(
        self,
        pipeline_result: ValidationPipelineResult,
        schema_metadata: Dict,
    ) -> RepairResult:
        """
        Takes a ValidationPipelineResult that failed validation, executes up to 3 repair cycles,
        and returns the RepairResult.
        """
        start_time = time.perf_counter()

        # Check for parser errors in the pipeline result
        parser_context = self.pipeline.parser.parse(pipeline_result.sql)
        if parser_context.errors:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return RepairResult(
                success=False,
                repaired=False,
                repaired_sql=pipeline_result.sql,
                repair_type="NONE",
                errors=parser_context.errors,
                status=RepairStatus.FAILED,
                duration_ms=duration_ms,
            )

        metadata = self.pipeline.metadata_extractor.extract(parser_context.ast)

        # Create repair context
        context = RepairContext(
            original_sql=pipeline_result.sql,
            current_sql=pipeline_result.sql,
            ast=parser_context.ast,
            metadata=metadata,
            schema_metadata=schema_metadata,
            validation_errors=pipeline_result.schema_result.errors if pipeline_result.schema_result else [],
            applied_repairs=[],
            repair_attempts=0,
            max_attempts=3,
        )

        final_validation = pipeline_result

        while context.repair_attempts < context.max_attempts:
            if not context.validation_errors:
                break

            repaired_in_attempt = False
            for strategy in self.strategies:
                if strategy.can_repair(context):
                    result = strategy.repair(context)
                    if result.success:
                        # Re-validate the repaired query using the validation pipeline
                        new_res = self.pipeline.validate(context.current_sql, schema_metadata)
                        final_validation = new_res

                        if new_res.passed:
                            context.validation_errors = []
                            context.ast = new_res.context.ast
                            context.metadata = new_res.metadata
                            repaired_in_attempt = True
                            break
                        else:
                            if new_res.schema_result:
                                context.validation_errors = new_res.schema_result.errors
                                context.ast = new_res.context.ast
                                context.metadata = new_res.metadata
                                repaired_in_attempt = True
                                break
                            else:
                                # Parsing or security validation failed after repair
                                duration_ms = (time.perf_counter() - start_time) * 1000
                                return RepairResult(
                                    success=False,
                                    repaired=False,
                                    repaired_sql=context.original_sql,
                                    repair_type="NONE",
                                    errors=[new_res.error] if new_res.error else ["Post-repair pipeline error."],
                                    final_context=context,
                                    final_validation=new_res,
                                    attempts=context.repair_attempts + 1,
                                    applied_repairs=context.applied_repairs,
                                    status=RepairStatus.FAILED,
                                    duration_ms=duration_ms,
                                )

            context.repair_attempts += 1
            if not repaired_in_attempt:
                break

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Check if validation now passes
        if not context.validation_errors and final_validation.passed:
            # Determine the main repair type
            repair_types = []
            for r in context.applied_repairs:
                reason_lower = r.reason.lower()
                if "column" in reason_lower:
                    repair_types.append("COLUMN")
                elif "table" in reason_lower:
                    repair_types.append("TABLE")
                elif "alias" in reason_lower:
                    repair_types.append("ALIAS")
                elif "ambiguous" in reason_lower or "qualified" in reason_lower:
                    repair_types.append("AMBIGUITY")

            combined_type = "+".join(set(repair_types)) if repair_types else "REPAIRED"

            return RepairResult(
                success=True,
                repaired=len(context.applied_repairs) > 0,
                repaired_sql=context.current_sql,
                repair_type=combined_type,
                candidate=context.applied_repairs[-1] if context.applied_repairs else None,
                final_context=context,
                final_validation=final_validation,
                attempts=context.repair_attempts,
                applied_repairs=context.applied_repairs,
                status=RepairStatus.REPAIRED,
                duration_ms=duration_ms,
            )
        else:
            status = RepairStatus.MAX_ATTEMPTS if context.repair_attempts >= context.max_attempts else RepairStatus.NOT_REPAIRABLE
            return RepairResult(
                success=False,
                repaired=False,
                repaired_sql=context.original_sql,
                repair_type="NONE",
                errors=[str(e) for e in context.validation_errors],
                final_context=context,
                final_validation=final_validation,
                attempts=context.repair_attempts,
                applied_repairs=context.applied_repairs,
                status=status,
                duration_ms=duration_ms,
            )
