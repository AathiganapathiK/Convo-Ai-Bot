import re
from typing import List, Set, Optional, TypeVar
from sqlglot import exp
from sqlglot.expressions import Expression, Expr

from ai.ast.models import (
    SQLMetadata,
    TableInfo,
    ColumnInfo,
    JoinInfo,
    AggregateInfo,
    OrderByInfo,
    PredicateInfo,
    WindowFunctionInfo,
)

T = TypeVar('T')


class SQLASTMetadataExtractor:
    """ 
    Extracts structural metadata from a parsed SQL AST.
    """

    def extract(self, ast: exp.Expression) -> SQLMetadata:
        """
        Analyze the SQL AST and extract all metadata components.

        Args:
            ast: The parsed SQL AST Expression from sqlglot.

        Returns:
            SQLMetadata object populated with query details.
        """
        if ast is None:
            return SQLMetadata()

        # 1. Extract CTEs first so we can filter them out from the referenced tables list
        ctes = self._deduplicate(self._extract_ctes(ast))
        cte_names = set(ctes)

        # 2. Extract structural query information using private helpers
        tables = self._deduplicate(self._extract_tables(ast, cte_names))
        columns = self._deduplicate(self._extract_columns(ast))
        joins = self._deduplicate(self._extract_joins(ast))
        aggregates = self._deduplicate(self._extract_aggregates(ast))
        group_by = self._deduplicate(self._extract_group_by(ast))
        order_by = self._deduplicate(self._extract_order_by(ast))
        where = self._deduplicate(self._extract_where(ast))
        having = self._deduplicate(self._extract_having(ast))
        window_functions = self._deduplicate(self._extract_windows(ast))
        subqueries = self._extract_subqueries(ast)
        limit = self._extract_limit(ast)

        # Extraction of validation specific fields (Phase 2 additions)
        join_columns = self._deduplicate(self._extract_join_columns(ast))
        where_columns = self._deduplicate(self._extract_where_columns(ast))
        group_by_columns = self._deduplicate(self._extract_group_by_columns(ast))
        having_columns = self._deduplicate(self._extract_having_columns(ast))
        order_by_columns = self._deduplicate(self._extract_order_by_columns(ast))
        cte_references = self._deduplicate(self._extract_cte_references(ast, cte_names))

        # 3. Assemble and return the metadata model
        return self._build_metadata(
            tables=tables,
            columns=columns,
            joins=joins,
            aggregates=aggregates,
            group_by=group_by,
            order_by=order_by,
            where=where,
            having=having,
            ctes=ctes,
            window_functions=window_functions,
            subqueries=subqueries,
            limit=limit,
            join_columns=join_columns,
            where_columns=where_columns,
            group_by_columns=group_by_columns,
            having_columns=having_columns,
            order_by_columns=order_by_columns,
            cte_references=cte_references
        )


    def _extract_tables(self, ast: exp.Expression, cte_names: Set[str]) -> List[TableInfo]:
        """
        Extract all table references, excluding temporary CTE table names.
        """
        tables = []
        for table in ast.find_all(exp.Table):
            if table.name in cte_names:
                continue
            tables.append(TableInfo(
                name=table.name,
                alias=table.alias if table.alias else None
            ))
        return tables

    def _extract_columns(self, ast: exp.Expression) -> List[ColumnInfo]:
        """
        Extract columns selected in the projection lists.
        """
        columns = []
        for select_node in ast.find_all(exp.Select):
            for proj in select_node.expressions:
                if isinstance(proj, exp.Column):
                    columns.append(ColumnInfo(
                        name=proj.name,
                        table=proj.text("table") if proj.text("table") else None,
                        alias=None
                    ))
                elif isinstance(proj, exp.Alias):
                    alias_name = proj.alias
                    inner = proj.this
                    if isinstance(inner, exp.Column):
                        columns.append(ColumnInfo(
                            name=inner.name,
                            table=inner.text("table") if inner.text("table") else None,
                            alias=alias_name if alias_name else None
                        ))
                    else:
                        for col in inner.find_all(exp.Column):
                            columns.append(ColumnInfo(
                                name=col.name,
                                table=col.text("table") if col.text("table") else None,
                                alias=alias_name if alias_name else None
                            ))
                elif isinstance(proj, exp.Star):
                    columns.append(ColumnInfo(name="*"))
                else:
                    for col in proj.find_all(exp.Column):
                        columns.append(ColumnInfo(
                            name=col.name,
                            table=col.text("table") if col.text("table") else None,
                            alias=None
                        ))
        return columns

    def _extract_joins(self, ast: exp.Expression) -> List[JoinInfo]:
        """
        Extract JOIN metadata: join type, referenced table, table alias, and condition.
        """
        joins = []
        for join_expr in ast.find_all(exp.Join):
            # Resolve join type name (e.g. INNER, LEFT, RIGHT OUTER, CROSS)
            side = join_expr.args.get("side")
            kind = join_expr.args.get("kind")
            method = join_expr.args.get("method")

            parts = []
            if side:
                parts.append(str(side).upper())
            if kind:
                parts.append(str(kind).upper())
            if method:
                parts.append(str(method).upper())

            join_type = " ".join(parts) if parts else "INNER"

            table_node = join_expr.find(exp.Table)
            on_node = join_expr.args.get("on")

            joins.append(JoinInfo(
                join_type=join_type,
                table=table_node.name if table_node else "",
                alias=table_node.alias if table_node and table_node.alias else None,
                condition=str(on_node) if on_node else ""
            ))
        return joins

    def _extract_aggregates(self, ast: exp.Expression) -> List[AggregateInfo]:
        """
        Extract aggregate function names (SUM, AVG, COUNT, MIN, MAX) and their target columns.
        """
        aggregates = []
        agg_types = {"Sum": "SUM", "Avg": "AVG", "Count": "COUNT", "Min": "MIN", "Max": "MAX"}
        for f in ast.find_all(exp.Func):
            func_name = type(f).__name__
            if func_name in agg_types:
                aggregates.append(AggregateInfo(
                    function=agg_types[func_name],
                    column=str(f.this) if f.this else ""
                ))
        return aggregates

    def _extract_group_by(self, ast: exp.Expression) -> List[str]:
        """
        Extract columns listed under GROUP BY clauses.
        """
        groups = []
        for g in ast.find_all(exp.Group):
            for expr in g.expressions:
                groups.append(str(expr))
        return groups

    def _extract_order_by(self, ast: exp.Expression) -> List[OrderByInfo]:
        """
        Extract sorting columns and directions (ASC, DESC) under ORDER BY clauses.
        """
        order_bys = []
        for o in ast.find_all(exp.Order):
            for x in o.expressions:
                direction = "DESC" if x.args.get("desc") else "ASC"
                order_bys.append(OrderByInfo(
                    column=str(x.this),
                    direction=direction
                ))
        return order_bys

    def _extract_where(self, ast: exp.Expression) -> List[PredicateInfo]:
        """
        Extract flat conditional predicates from WHERE clauses.
        """
        predicates = []
        for w in ast.find_all(exp.Where):
            for cond in self._flatten_conditions(w.this):
                predicates.append(PredicateInfo(expression=cond))
        return predicates

    def _extract_having(self, ast: exp.Expression) -> List[PredicateInfo]:
        """
        Extract flat conditional predicates from HAVING clauses.
        """
        predicates = []
        for h in ast.find_all(exp.Having):
            for cond in self._flatten_conditions(h.this):
                predicates.append(PredicateInfo(expression=cond))
        return predicates

    def _extract_ctes(self, ast: exp.Expression) -> List[str]:
        """
        Extract list of CTE aliases defined in the query.
        """
        return [cte.alias for cte in ast.find_all(exp.CTE) if cte.alias]

    def _extract_windows(self, ast: exp.Expression) -> List[WindowFunctionInfo]:
        """
        Extract window function types (e.g. ROW_NUMBER, RANK, DENSE_RANK).
        """
        windows = []
        for w in ast.find_all(exp.Window):
            if w.this:
                func_name = self._camel_to_snake(type(w.this).__name__)
                windows.append(WindowFunctionInfo(function=func_name))
        return windows

    def _extract_subqueries(self, ast: exp.Expression) -> int:
        """
        Count the total number of table, scalar, IN, or EXISTS subqueries in the AST.
        """
        subquery_nodes = len(list(ast.find_all(exp.Subquery)))
        exists_nodes = len(list(ast.find_all(exp.Exists)))
        return subquery_nodes + exists_nodes

    def _extract_limit(self, ast: exp.Expression) -> Optional[int]:
        """
        Extract the LIMIT/TOP integer value.
        """
        limit_node = ast.find(exp.Limit)
        if limit_node and limit_node.expression:
            try:
                return int(limit_node.expression.this)
            except (ValueError, TypeError):
                pass
        return None

    def _flatten_conditions(self, node: Expr | Expression) -> List[str]:
        """
        Helper method to split And nodes recursively into individual predicate strings.
        """
        if isinstance(node, exp.And):
            return self._flatten_conditions(node.left) + self._flatten_conditions(node.right)
        return [node.sql()]

    def _camel_to_snake(self, name: str) -> str:
        """
        Helper method to convert CamelCase names to UPPER_SNAKE_CASE.
        """
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).upper()

    def _build_metadata(
        self,
        tables: List[TableInfo],
        columns: List[ColumnInfo],
        joins: List[JoinInfo],
        aggregates: List[AggregateInfo],
        group_by: List[str],
        order_by: List[OrderByInfo],
        where: List[PredicateInfo],
        having: List[PredicateInfo],
        ctes: List[str],
        window_functions: List[WindowFunctionInfo],
        subqueries: int,
        limit: Optional[int],
        join_columns: List[ColumnInfo] | None = None,
        where_columns: List[ColumnInfo] | None = None,
        group_by_columns: List[ColumnInfo] | None = None,
        having_columns: List[ColumnInfo] | None = None,
        order_by_columns: List[ColumnInfo] | None = None,
        cte_references: List[TableInfo] | None = None
    ) -> SQLMetadata:
        """
        Assemble the final SQLMetadata dataclass container.
        """
        return SQLMetadata(
            tables=tables,
            selected_columns=columns,
            joins=joins,
            aggregates=aggregates,
            group_by=group_by,
            order_by=order_by,
            where=where,
            having=having,
            ctes=ctes,
            window_functions=window_functions,
            subquery_count=subqueries,
            limit=limit,
            join_columns=join_columns or [],
            where_columns=where_columns or [],
            group_by_columns=group_by_columns or [],
            having_columns=having_columns or [],
            order_by_columns=order_by_columns or [],
            cte_references=cte_references or []
        )

    def _deduplicate(self, items: List[T]) -> List[T]:
        """
        Deduplicate list elements while preserving insertion order.
        """
        unique: List[T] = []
        for item in items:
            if item not in unique:
                unique.append(item)
        return unique

    def _extract_join_columns(self, ast: exp.Expression) -> List[ColumnInfo]:
        columns = []
        for join_expr in ast.find_all(exp.Join):
            on_node = join_expr.args.get("on")
            if on_node:
                for col in on_node.find_all(exp.Column):
                    columns.append(ColumnInfo(
                        name=col.name,
                        table=col.text("table") if col.text("table") else None
                    ))
        return columns

    def _extract_where_columns(self, ast: exp.Expression) -> List[ColumnInfo]:
        columns = []
        for w in ast.find_all(exp.Where):
            for col in w.find_all(exp.Column):
                columns.append(ColumnInfo(
                    name=col.name,
                    table=col.text("table") if col.text("table") else None
                ))
        return columns

    def _extract_group_by_columns(self, ast: exp.Expression) -> List[ColumnInfo]:
        columns = []
        for g in ast.find_all(exp.Group):
            for expr in g.expressions:
                for col in expr.find_all(exp.Column):
                    columns.append(ColumnInfo(
                        name=col.name,
                        table=col.text("table") if col.text("table") else None
                    ))
        return columns

    def _extract_having_columns(self, ast: exp.Expression) -> List[ColumnInfo]:
        columns = []
        for h in ast.find_all(exp.Having):
            for col in h.find_all(exp.Column):
                columns.append(ColumnInfo(
                    name=col.name,
                    table=col.text("table") if col.text("table") else None
                ))
        return columns

    def _extract_order_by_columns(self, ast: exp.Expression) -> List[ColumnInfo]:
        columns = []
        for o in ast.find_all(exp.Order):
            for x in o.expressions:
                for col in x.find_all(exp.Column):
                    columns.append(ColumnInfo(
                        name=col.name,
                        table=col.text("table") if col.text("table") else None
                    ))
        return columns

    def _extract_cte_references(self, ast: exp.Expression, cte_names: Set[str]) -> List[TableInfo]:
        cte_refs = []
        for table in ast.find_all(exp.Table):
            if table.name in cte_names:
                cte_refs.append(TableInfo(
                    name=table.name,
                    alias=table.alias if table.alias else None
                ))
        return cte_refs