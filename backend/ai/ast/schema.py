from dataclasses import dataclass, field
from enum import Enum

from .models import SQLMetadata, ColumnInfo


class ValidationErrorCode(str, Enum):
    """
    Standardized classification codes for schema validation errors.
    """
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"
    COLUMN_NOT_RESOLVED = "COLUMN_NOT_RESOLVED"
    COLUMN_AMBIGUOUS = "COLUMN_AMBIGUOUS"
    ALIAS_NOT_FOUND = "ALIAS_NOT_FOUND"


@dataclass
class SchemaValidationError:
    """
    Structured model for schema validation errors.
    Decouples error classification and repair details from plain-text formatting.
    """
    code: ValidationErrorCode
    message: str
    column: str | None = None
    table: str | None = None
    possible_tables: list[str] = field(default_factory=list)
    clause: str | None = None

    def __str__(self) -> str:
        return self.message

    def lower(self) -> str:
        return self.message.lower()


@dataclass
class SchemaValidationResult:
    passed: bool
    errors: list[SchemaValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SQLASTSchemaValidator:
    """
    Validates SQLMetadata against synchronized database schema.

    This validator ONLY validates schema.
    It does not parse SQL.
    It does not modify SQL.
    It does not execute SQL.
    """

    def validate(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
    ) -> SchemaValidationResult:
        """
        Accept SQLMetadata and synchronized schema metadata, build alias map,
        run all validation phases in order, collect errors, and return a SchemaValidationResult.
        """
        errors: list[SchemaValidationError] = []
        warnings: list[str] = []

        # 1. Validate Tables (Validation Order: Tables)
        self._validate_tables(metadata, schema_metadata, errors, warnings)
        if errors:
            return self._build_result(self._deduplicate_errors(errors), warnings)

        # 2. Build alias map
        alias_map = self._build_alias_map(metadata)

        # 3. Validate Aliases (Validation Order: Aliases)
        self._validate_aliases(metadata, schema_metadata, alias_map, errors, warnings)
        if errors:
            return self._build_result(self._deduplicate_errors(errors), warnings)

        # 4. Validate Columns across clauses in order
        self._validate_selected_columns(metadata, schema_metadata, alias_map, errors, warnings)
        self._validate_join_columns(metadata, schema_metadata, alias_map, errors, warnings)
        self._validate_where_columns(metadata, schema_metadata, alias_map, errors, warnings)
        self._validate_group_by_columns(metadata, schema_metadata, alias_map, errors, warnings)
        self._validate_having_columns(metadata, schema_metadata, alias_map, errors, warnings)
        self._validate_order_by_columns(metadata, schema_metadata, alias_map, errors, warnings)

        # 5. Deduplicate and return final result
        unique_errors = self._deduplicate_errors(errors)
        return self._build_result(unique_errors, warnings)

    def _validate_tables(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
        errors: list[SchemaValidationError],
        warnings: list[str],
    ) -> None:
        """
        Validates that all tables in FROM and JOIN clauses exist in the schema metadata.
        """
        for table in metadata.tables:
            if not self._table_exists(table.name, schema_metadata, metadata.ctes):
                errors.append(
                    SchemaValidationError(
                        code=ValidationErrorCode.TABLE_NOT_FOUND,
                        message=f"Table '{table.name}' does not exist.",
                        table=table.name,
                    )
                )

        for join in metadata.joins:
            if not self._table_exists(join.table, schema_metadata, metadata.ctes):
                errors.append(
                    SchemaValidationError(
                        code=ValidationErrorCode.TABLE_NOT_FOUND,
                        message=f"Table '{join.table}' does not exist.",
                        table=join.table,
                    )
                )

    def _validate_aliases(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
        errors: list[SchemaValidationError],
        warnings: list[str],
    ) -> None:
        """
        Verify all table aliases/prefixes referenced in column references actually exist in the query.
        """
        all_columns = (
            metadata.selected_columns
            + metadata.join_columns
            + metadata.where_columns
            + metadata.group_by_columns
            + metadata.having_columns
            + metadata.order_by_columns
        )

        for col in all_columns:
            if col.table:
                alias_lower = col.table.lower()

                # Check if it matches an alias in alias_map
                in_alias_map = any(k.lower() == alias_lower for k in alias_map)

                # Check if it matches any table name, base name, or CTE name directly
                is_direct_table = False
                for t in metadata.tables:
                    if t.name.lower() == alias_lower or t.name.split(".")[-1].lower() == alias_lower:
                        is_direct_table = True
                for j in metadata.joins:
                    if j.table.lower() == alias_lower or j.table.split(".")[-1].lower() == alias_lower:
                        is_direct_table = True
                for cte in metadata.ctes:
                    if cte.lower() == alias_lower:
                        is_direct_table = True

                if not in_alias_map and not is_direct_table:
                    errors.append(
                        SchemaValidationError(
                            code=ValidationErrorCode.ALIAS_NOT_FOUND,
                            message=(
                                f"Alias or table '{col.table}' used in column reference '{col.table}.{col.name}' "
                                f"does not exist in FROM/JOIN."
                            ),
                            column=col.name,
                            table=col.table,
                        )
                    )

    def _validate_column_reference(
        self,
        col: ColumnInfo,
        clause_name: str,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
        errors: list[SchemaValidationError],
        warnings: list[str],
        allow_select_alias: bool = False,
    ) -> None:
        """
        Validates a single column reference against resolved tables/schema/CTEs/select-aliases.
        """
        if allow_select_alias:
            is_selected_alias = any(
                col_info.alias and col_info.alias.lower() == col.name.lower()
                for col_info in metadata.selected_columns
            )
            if is_selected_alias:
                return

        resolved_table, possible_tables = self._resolve_column_table(
            col.name, col.table, metadata, schema_metadata, alias_map
        )

        # Handle ambiguous column references
        if not col.table and len(possible_tables) > 1:
            found_tables_str = "\n".join(f"- {t}" for t in possible_tables)
            errors.append(
                SchemaValidationError(
                    code=ValidationErrorCode.COLUMN_AMBIGUOUS,
                    message=(
                        f"Ambiguous column '{col.name}'.\n"
                        f"Found in:\n"
                        f"{found_tables_str}\n"
                        f"Qualify the column using a table alias."
                    ),
                    column=col.name,
                    possible_tables=possible_tables,
                    clause=clause_name,
                )
            )
            return

        if not resolved_table:
            errors.append(
                SchemaValidationError(
                    code=ValidationErrorCode.COLUMN_NOT_RESOLVED,
                    message=(
                        f"Column '{col.name}' cannot be resolved to any table in the query."
                        if clause_name == "SELECT"
                        else f"Column '{col.name}' in {clause_name} cannot be resolved to any table."
                    ),
                    column=col.name,
                    clause=clause_name,
                )
            )
            return

        if any(cte.lower() == resolved_table.lower() for cte in metadata.ctes):
            return

        if not self._column_exists(resolved_table, col.name, schema_metadata):
            errors.append(
                SchemaValidationError(
                    code=ValidationErrorCode.COLUMN_NOT_FOUND,
                    message=(
                        f"Column '{col.name}' does not exist on table '{resolved_table}'."
                        if clause_name == "SELECT"
                        else f"Column '{col.name}' does not exist on table '{resolved_table}' in {clause_name}."
                    ),
                    column=col.name,
                    table=resolved_table,
                    clause=clause_name,
                )
            )

    def _validate_selected_columns(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
        errors: list[SchemaValidationError],
        warnings: list[str],
    ) -> None:
        """
        Verify all selected columns exist on their resolved tables.
        """
        for col in metadata.selected_columns:
            if col.name == "*":
                continue
            self._validate_column_reference(
                col, "SELECT", metadata, schema_metadata, alias_map, errors, warnings
            )

    def _validate_join_columns(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
        errors: list[SchemaValidationError],
        warnings: list[str],
    ) -> None:
        """
        Verify columns used in JOIN conditions exist on their respective tables.
        """
        for col in metadata.join_columns:
            self._validate_column_reference(
                col, "JOIN condition", metadata, schema_metadata, alias_map, errors, warnings
            )

    def _validate_where_columns(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
        errors: list[SchemaValidationError],
        warnings: list[str],
    ) -> None:
        """
        Verify columns in WHERE clauses exist on their respective tables.
        """
        for col in metadata.where_columns:
            self._validate_column_reference(
                col, "WHERE clause", metadata, schema_metadata, alias_map, errors, warnings
            )

    def _validate_group_by_columns(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
        errors: list[SchemaValidationError],
        warnings: list[str],
    ) -> None:
        """
        Verify columns in GROUP BY clauses exist on their respective tables or match select aliases.
        """
        for col in metadata.group_by_columns:
            self._validate_column_reference(
                col,
                "GROUP BY clause",
                metadata,
                schema_metadata,
                alias_map,
                errors,
                warnings,
                allow_select_alias=True,
            )

    def _validate_having_columns(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
        errors: list[SchemaValidationError],
        warnings: list[str],
    ) -> None:
        """
        Verify columns in HAVING clauses exist on their respective tables or match select aliases.
        """
        for col in metadata.having_columns:
            self._validate_column_reference(
                col,
                "HAVING clause",
                metadata,
                schema_metadata,
                alias_map,
                errors,
                warnings,
                allow_select_alias=True,
            )

    def _validate_order_by_columns(
        self,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
        errors: list[SchemaValidationError],
        warnings: list[str],
    ) -> None:
        """
        Verify columns in ORDER BY clauses exist on their respective tables or match select aliases.
        """
        for col in metadata.order_by_columns:
            self._validate_column_reference(
                col,
                "ORDER BY clause",
                metadata,
                schema_metadata,
                alias_map,
                errors,
                warnings,
                allow_select_alias=True,
            )

    def _resolve_table_name(self, table_name: str, schema_metadata: dict) -> str | None:
        """
        Resolves table_name to its fully qualified name in schema_metadata.
        Handles case-insensitivity and prefix matching (e.g. "Sales" -> "dbo.Sales").
        """
        if not table_name:
            return None

        table_name_lower = table_name.lower()

        # 1. Exact/case-insensitive match on full key (e.g. "dbo.Sales" or "dbo.sales")
        for key in schema_metadata:
            if key.lower() == table_name_lower:
                return key

        # 2. Match on base name if no schema is specified (e.g. "Sales" matches "dbo.Sales")
        if "." not in table_name:
            for key in schema_metadata:
                base_name = key.split(".")[-1].lower()
                if base_name == table_name_lower:
                    return key

        return None

    def _resolve_column_table(
        self,
        column_name: str,
        table_ref: str | None,
        metadata: SQLMetadata,
        schema_metadata: dict,
        alias_map: dict[str, str],
    ) -> tuple[str | None, list[str]]:
        """
        Resolves a column's table reference to a fully qualified table name.
        If table_ref is None, checks all tables in the query to find where the column exists.
        Returns a tuple of (resolved_table_name, list_of_possible_tables).
        """
        if table_ref:
            mapped_table = self._lookup_alias(table_ref, alias_map)
            if mapped_table:
                if any(cte.lower() == mapped_table.lower() for cte in metadata.ctes):
                    return mapped_table, [mapped_table]
                resolved = self._resolve_table_name(mapped_table, schema_metadata)
                return resolved, [resolved] if resolved else []

            if any(cte.lower() == table_ref.lower() for cte in metadata.ctes):
                return table_ref, [table_ref]
            resolved = self._resolve_table_name(table_ref, schema_metadata)
            return resolved, [resolved] if resolved else []

        # If no table_ref is specified, search all tables in the query
        possible_tables = []
        tables_to_search = []
        for t in metadata.tables:
            tables_to_search.append(t.name)
        for j in metadata.joins:
            tables_to_search.append(j.table)
        for cte in metadata.ctes:
            tables_to_search.append(cte)

        # Deduplicate tables_to_search
        unique_tables_to_search = []
        for t in tables_to_search:
            if t.lower() not in [ut.lower() for ut in unique_tables_to_search]:
                unique_tables_to_search.append(t)

        for table_name in unique_tables_to_search:
            if any(cte.lower() == table_name.lower() for cte in metadata.ctes):
                continue

            resolved = self._resolve_table_name(table_name, schema_metadata)
            if resolved:
                if self._column_exists(resolved, column_name, schema_metadata):
                    possible_tables.append(resolved)

        # If no physical tables match the column, only then consider CTEs
        if not possible_tables:
            for table_name in unique_tables_to_search:
                if any(cte.lower() == table_name.lower() for cte in metadata.ctes):
                    possible_tables.append(table_name)

        if len(possible_tables) == 1:
            return possible_tables[0], possible_tables
        elif len(possible_tables) > 1:
            # Ambiguous column reference!
            return None, possible_tables

        # If it could not be resolved to any table because it doesn't exist,
        # but there is exactly one table/CTE in the query, default to that table/CTE
        # so we can provide a specific "does not exist on table X" error message.
        if len(unique_tables_to_search) == 1:
            tbl = unique_tables_to_search[0]
            if any(cte.lower() == tbl.lower() for cte in metadata.ctes):
                return tbl, [tbl]
            resolved = self._resolve_table_name(tbl, schema_metadata)
            return resolved, [resolved] if resolved else []

        return None, []

    def _column_exists(self, table_name: str, column_name: str, schema_metadata: dict) -> bool:
        """
        Checks if a column exists in the schema metadata for the given table.
        """
        if table_name in schema_metadata:
            cols = schema_metadata[table_name].get("columns", set())
            return column_name.lower() in cols
        return False

    def _table_exists(self, table_name: str, schema_metadata: dict, ctes: list[str]) -> bool:
        """
        Checks if a table exists either as a CTE or in the schema metadata.
        """
        if any(cte.lower() == table_name.lower() for cte in ctes):
            return True
        return self._resolve_table_name(table_name, schema_metadata) is not None

    def _build_alias_map(self, metadata: SQLMetadata) -> dict[str, str]:
        """
        Builds a mapping from table aliases to their full table name as written in query.
        Example output: {"S": "Sales", "P": "Products", "C": "SalesCTE"}
        """
        alias_map = {}

        # FROM clause tables
        for table in metadata.tables:
            if table.alias:
                alias_map[table.alias] = table.name

        # JOIN clause tables
        for join in metadata.joins:
            if join.alias:
                alias_map[join.alias] = join.table

        # CTE references
        for cte in metadata.cte_references:
            if cte.alias:
                alias_map[cte.alias] = cte.name

        return alias_map

    def _lookup_alias(self, alias: str, alias_map: dict[str, str]) -> str | None:
        """
        Helper method to lookup alias case-insensitively.
        """
        if not alias:
            return None
        alias_lower = alias.lower()
        for k, v in alias_map.items():
            if k.lower() == alias_lower:
                return v
        return None

    def _deduplicate_errors(self, errors: list[SchemaValidationError]) -> list[SchemaValidationError]:
        """
        Deduplicates errors while preserving order.
        """
        unique_errors = []
        for err in errors:
            if err not in unique_errors:
                unique_errors.append(err)
        return unique_errors

    def _build_result(self, errors: list[SchemaValidationError], warnings: list[str]) -> SchemaValidationResult:
        """
        Constructs the SchemaValidationResult object.
        """
        return SchemaValidationResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )