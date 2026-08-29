from dataclasses import dataclass, field
from typing import Optional

from ai.ast.exceptions import ASTParserError
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
        #
        # SQLASTParser signals a parse failure by raising ASTParserError rather
        # than returning a context with errors populated. ASTParserError is not
        # an EnterpriseException, so letting it escape sent unparseable SQL to
        # the generic handler and produced an HTTP 500 instead of the ordinary
        # validation error - and the query was never recorded as a validation
        # failure. Converting it here keeps every failure on one path.
        #
        # Behaviour is unchanged for the caller in every other respect, and the
        # query is still rejected: malformed SQL has never reached execution
        # and still does not.
        try:
            context = self.parser.parse(sql)
        except ASTParserError as ex:
            context = ValidationContext(original_sql=sql)
            context.errors.append(str(ex))

            return ValidationPipelineResult(
                passed=False,
                sql=sql,
                context=context,
                error=f"SQL could not be parsed: {ex}",
            )

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
