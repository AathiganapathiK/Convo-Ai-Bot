from ai.insights.data_shape import DataShape


class DataShapeClassifier:

    @staticmethod
    def classify(
    rows,
    question: str = ""
    ):
        question_lower = question.lower()

        if not rows:
            return DataShape.SINGLE_VALUE

        row_count = len(rows)

        first_row = rows[0]

        columns = [
            str(col).lower()
            for col in first_row.keys()
        ]

        date_keywords = [
            "date",
            "month",
            "year",
            "quarter",
            "week"
        ]

        ranking_keywords = [
            "top",
            "highest",
            "lowest",
            "best",
            "worst",
            "rank",
            "ranking"
        ]

        has_date_column = any(
            any(
                keyword in column
                for keyword in date_keywords
            )
            for column in columns
        )



        if row_count == 1:
            return DataShape.SINGLE_VALUE
        
        if any(
            keyword in question_lower
            for keyword in ranking_keywords
        ):
            return DataShape.RANKED_LIST
        
        if row_count > 50:
            return DataShape.LARGE_SUMMARY

        if (
            has_date_column
            and row_count <= 36
        ):
            return DataShape.TREND

        if row_count <= 10:
            return DataShape.COMPARISON

        return DataShape.RANKED_LIST