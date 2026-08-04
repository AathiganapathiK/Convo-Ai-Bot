from dataclasses import dataclass, field
from typing import Optional

from ai.ast.models import ValidationContext, SQLMetadata
from ai.ast.schema import SchemaValidationResult
from ai.ast.security import SecurityValidationResult


@dataclass
class ValidationPipelineResult:
    """
    Result containing status and context for the full SQL validation pipeline.
    """
    passed: bool
    sql: str
    context: ValidationContext
    metadata: Optional[SQLMetadata] = None
    security_result: Optional[SecurityValidationResult] = None
    schema_result: Optional[SchemaValidationResult] = None
    error: Optional[str] = None


class ValidationPipeline:
    """
    Executes the sequential SQL validation steps:
    SQL -> Parser -> Security -> Metadata Extraction -> Schema Validation.
    """

    def __init__(
        self,
        parser,
        security_validator,
        metadata_extractor,
        schema_validator,
    ):
        self.parser = parser
        self.security_validator = security_validator
        self.metadata_extractor = metadata_extractor
        self.schema_validator = schema_validator

    def validate(self, sql: str, schema_metadata: dict) -> ValidationPipelineResult:
        # Step 1: Parse AST
        context = self.parser.parse(sql)
        if context.errors:
            return ValidationPipelineResult(
                passed=False,
                sql=sql,
                context=context,
                error=context.errors[0],
            )
        if not context.ast:
            return ValidationPipelineResult(
                passed=False,
                sql=sql,
                context=context,
                error="Failed to build SQL AST.",
            )

        # Step 2: Security Validation
        security = self.security_validator.validate_ast(context.ast)
        if not security.passed:
            return ValidationPipelineResult(
                passed=False,
                sql=sql,
                context=context,
                security_result=security,
                error=security.errors[0],
            )

        # Step 3: Metadata Extraction
        metadata = self.metadata_extractor.extract(context.ast)
        context.metadata = metadata

        # Step 4: Schema Validation
        schema = self.schema_validator.validate(metadata, schema_metadata)
        if not schema.passed:
            return ValidationPipelineResult(
                passed=False,
                sql=sql,
                context=context,
                metadata=metadata,
                security_result=security,
                schema_result=schema,
                error=str(schema.errors[0]) if schema.errors else "Schema validation failed.",
            )

        return ValidationPipelineResult(
            passed=True,
            sql=sql,
            context=context,
            metadata=metadata,
            security_result=security,
            schema_result=schema,
        )
