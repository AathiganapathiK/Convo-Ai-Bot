from semantic.relationship_service import (
    SemanticRelationshipService
)


class RelationshipContextService:

    @staticmethod
    def build_context(
        connection_id,
        relevant_tables
    ):

        rows = (
            SemanticRelationshipService
            .build_relationships(
                connection_id
            )
        )
        filtered_rows = []

        relevant_tables = set(relevant_tables)

        for row in rows:

            left_table = row[0]
            right_table = row[2]

            if (
                left_table in relevant_tables
                and
                right_table in relevant_tables
            ):

                filtered_rows.append(row)

        if not filtered_rows:
            return ""

        context = (
            "Relationship Context\n"
            "--------------------\n\n"
        )

        for row in filtered_rows:

            left_table = row[0]
            left_column = row[1]
            right_table = row[2]
            right_column = row[3]
    
            context += (
                f"INNER JOIN {right_table}\n"
                f"ON {left_table}.{left_column} = "
                f"{right_table}.{right_column}\n\n"
            )

        return context.strip()