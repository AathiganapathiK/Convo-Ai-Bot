from abc import ABC, abstractmethod
from typing import Dict, Optional
from .models import RepairContext
from .result import RepairResult


class BaseRepairStrategy(ABC):
    """
    Common interface for all SQL repair strategies.
    """

    priority: int = 100

    @abstractmethod
    def can_repair(self, context: RepairContext) -> bool:
        """
        Check if this strategy is capable of repairing the validation errors in the context.
        """
        pass

    @abstractmethod
    def repair(self, context: RepairContext) -> RepairResult:
        """
        Execute the repair on the SQL AST, update the context, and return the result.
        """
        pass

    def _resolve_table_name(self, table_name: str, schema_metadata: Dict) -> Optional[str]:
        """
        Resolve a table name to its fully qualified name in schema metadata.
        """
        if not table_name:
            return None
        table_name_lower = table_name.lower()
        for key in schema_metadata:
            if key.lower() == table_name_lower:
                return key
        if "." not in table_name:
            for key in schema_metadata:
                base_name = key.split(".")[-1].lower()
                if base_name == table_name_lower:
                    return key
        return None

    def _build_alias_map(self, context: RepairContext) -> Dict[str, str]:
        """
        Build an alias map from metadata.
        Keys are upper-case for easy case-insensitive lookups.
        """
        alias_map = {}
        # From tables
        for table in context.metadata.tables:
            if table.alias:
                alias_map[table.alias.upper()] = table.name
        # Joins
        for join in context.metadata.joins:
            if join.alias:
                alias_map[join.alias.upper()] = join.table
        # CTEs
        for cte in context.metadata.cte_references:
            if cte.alias:
                alias_map[cte.alias.upper()] = cte.name
        return alias_map
