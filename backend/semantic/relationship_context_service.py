import webbrowser
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

        context = "Relationships:\n"

        for row in filtered_rows:

            context += (
                f"- {row[0]}.{row[1]}"
                f" -> "
                f"{row[2]}.{row[3]}\n"
            )

        return context