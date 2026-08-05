from sqlalchemy import text
from database import engine

class SemanticContextService:

    @staticmethod
    def build_context(metric_objects, dimension_objects, dialect=None):

        metric_objects = metric_objects or []
        dimension_objects = dimension_objects or []

        lines = []

        if metric_objects:

            lines.append("Relevant Metrics:")

            for metric in metric_objects:

                lines.append(
                    f"- {metric['business_name']}"
                )
                lines.append(
                    f"  Table: {metric['table_name']}"
                )
                lines.append(
                    f"  Column: {metric['column_name']}"
                )
                lines.append(
                    f"  Aggregation: {metric['aggregation_type']}"
                )
                lines.append("")

        if dimension_objects:

            lines.append("Relevant Dimensions:")

            for dimension in dimension_objects:

                lines.append(
                    f"- {dimension['business_name']}"
                )
                lines.append(
                    f"  Table: {dimension['table_name']}"
                )
                
                category = dimension.get("semantic_category")
                col_name = dimension["column_name"]
                
                if category and category.startswith("TIME_") and dialect:
                    from semantic.sql.temporal_mapper import TemporalMapper
                    sql_expr = TemporalMapper.get_sql_expression(dialect, category, col_name)
                    lines.append(
                        f"  Column: {col_name}"
                    )
                    lines.append(
                        f"  SQL Expression: {sql_expr}"
                    )
                else:
                    lines.append(
                        f"  Column: {col_name}"
                    )
                lines.append("")

        return "\n".join(lines)