from lib2to3.fixes import fix_throw
from sqlalchemy import text
import re
from database import engine


class DimensionValueResolver:
    """
    Resolves business values mentioned in a user's question
    using the semantic dimension value index.
    """

    @staticmethod
    def resolve(
        connection_id: str,
        question: str
    ):
        """
        Public entry point.

        Phase 1:
        - Normalize question
        - Load indexed values
        - Find exact matches
        """

        normalized_question = (
            DimensionValueResolver._normalize_question(
                question
            )
        )

        indexed_values = (
            DimensionValueResolver._load_dimension_values(
                connection_id
            )
        )

        matches = (
            DimensionValueResolver._find_exact_matches(
                normalized_question,
                indexed_values
            )
        )

        matches = DimensionValueResolver._remove_contained_matches(matches)

        return matches

    @staticmethod
    def _normalize_question(
        question: str
    ):
        """
        Normalize a user question for semantic matching.

        Phase 1:
        - Handle None safely
        - Trim whitespace
        - Convert to lowercase
        - Collapse multiple spaces
        """

        if question is None:
            return ""

        # Remove leading/trailing whitespace
        question = question.strip()

        # Convert to lowercase
        question = question.lower()

        # Collapse multiple spaces
        question = re.sub(r"\s+", " ", question)

        return question

    @staticmethod
    def _load_dimension_values(
        connection_id: str
    ):
        """
        Load all indexed semantic values for a connection.
        """

        query = text("""
            SELECT
                dvi.semantic_dimension_id,
                sd.business_name,
                sd.table_name,
                sd.column_name,
                dvi.value,
                dvi.normalized_value
            FROM dimension_value_index dvi
            INNER JOIN semantic_dimensions sd 
                ON sd.dimension_id = dvi.semantic_dimension_id
            WHERE
                dvi.connection_id = :connection_id
                AND sd.is_active = 1
            ORDER BY
                sd.business_name,
                dvi.value
        """)

        with engine.connect() as conn:

            result = conn.execute(
                query,
                {
                    "connection_id": connection_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]



    @staticmethod
    def _find_exact_matches(
        normalized_question: str,
        indexed_values: list
    ):
        """
        Find exact semantic value matches within the normalized question.
        """
        MIN_VALUE_LENGTH = 2

        matches = []

        for row in indexed_values:

            normalized_value = row["normalized_value"]

            if not normalized_value:
                continue
            
            # Skip very short values — too noisy
            if len(normalized_value.strip()) < MIN_VALUE_LENGTH:
                continue

            pattern = r"\b" + re.escape(normalized_value) + r"\b"

            if re.search(pattern, normalized_question):

                matches.append(
                    {
                        "dimension_id": row["semantic_dimension_id"],
                        "business_name": row["business_name"],
                        "table_name": row["table_name"],
                        "column_name": row["column_name"],
                        "value": row["value"],
                        "normalized_value": row["normalized_value"],
                        "confidence": 1.0
                    }
                )

        return matches

    @staticmethod
    def _remove_contained_matches(matches: list):
        """
        Remove semantic matches that are fully contained
        inside a longer matched value.
        """

        if len(matches) <= 1:
            return matches

        matches = sorted(
            matches,
            key=lambda m: len(m["normalized_value"]),
            reverse=True
        )

        filtered = []

        for candidate in matches:

            contained = False

            for kept in filtered:

                if candidate["normalized_value"] in kept["normalized_value"]:
                    contained = True
                    break

            if not contained:
                filtered.append(candidate)

        return filtered

    @staticmethod
    def _filter_metric_conflicts(
        value_matches: list,
        metric_objects: list
    ) -> list:
        """
        Remove dimension value matches that duplicate already
        resolved metrics.
        """

        metric_names = set()

        for metric in metric_objects:
            if metric.get("metric_name"):
                metric_names.add(metric["metric_name"].lower())

            if metric.get("business_name"):
                metric_names.add(metric["business_name"].lower())

        return [
            match
            for match in value_matches
            if match["normalized_value"] not in metric_names
        ]