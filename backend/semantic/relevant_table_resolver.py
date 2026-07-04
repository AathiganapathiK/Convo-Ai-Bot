from semantic.semantic_resolver import SemanticResolver


class RelevantTableResolver:

    @staticmethod
    def resolve(
        connection_id,
        question
    ):

        semantic_result = (
            SemanticResolver.resolve(
                connection_id,
                question
            )
        )

        tables = set()

        for metric in semantic_result["metric_objects"]:

            tables.add(
                metric["table_name"]
            )

        for dimension in semantic_result["dimension_objects"]:

            tables.add(
                dimension["table_name"]
            )


    
        return sorted(list(tables))