class RelevantTableResolver:

    METRIC_WEIGHT = 5
    DIMENSION_WEIGHT = 3
    VALUE_WEIGHT = 2

    @staticmethod
    def resolve(
        semantic_result
    ):

        table_scores = {}

        # Score metric tables
        for metric in semantic_result["metric_objects"]:

            table_name = metric["table_name"]

            table_scores[table_name] = (
                table_scores.get(table_name, 0)
                + RelevantTableResolver.METRIC_WEIGHT
            )

        # Score dimension tables
        for dimension in semantic_result["dimension_objects"]:

            table_name = dimension["table_name"]

            table_scores[table_name] = (
                table_scores.get(table_name, 0)
                + RelevantTableResolver.DIMENSION_WEIGHT
            )

        # Score value match tables
        for value in semantic_result["value_matches"]:

            table_name = value["table_name"]

            table_scores[table_name] = (
                table_scores.get(table_name, 0)
                + RelevantTableResolver.VALUE_WEIGHT
            )

        ranked_tables = [
            {
                "table_name": table_name,
                "score": score
            }
            for table_name, score in table_scores.items()
        ]

        ranked_tables.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return ranked_tables