from ai.insights.data_shape import DataShape
from utils.value_formatter import format_value

class SmartSerializer:

    @staticmethod
    def serialize(
        rows,
        shape: DataShape,
        max_rows: int = 20
    ):
        if not rows:
            return "No data returned."

        if shape == DataShape.SINGLE_VALUE:
            return SmartSerializer._single_value(rows)

        if shape == DataShape.TREND:
            return SmartSerializer._table(rows, max_rows)

        if shape == DataShape.COMPARISON:
            return SmartSerializer._table(rows, max_rows)

        if shape == DataShape.RANKED_LIST:
            return SmartSerializer._table(rows, max_rows)

        return SmartSerializer._large_summary(
            rows,
            max_rows
        )

    @staticmethod
    def _single_value(rows):

        row = rows[0]

        output = []

        for key, value in row.items():
            output.append(
                f"{key}: {format_value(key, value)}"
            )

        return "\n".join(output)

    @staticmethod
    def _table(
        rows,
        max_rows
    ):

        rows = rows[:max_rows]

        headers = list(rows[0].keys())

        output = []

        output.append(
            " | ".join(headers)
        )

        output.append(
            "-" * 50
        )

        for row in rows:

            output.append(
                " | ".join(
                    str(format_value(col, row.get(col)))
                    for col in headers
                )
            )

        return "\n".join(output)

    @staticmethod
    def _large_summary(
        rows,
        max_rows
    ):

        sample_rows = rows[:max_rows]

        headers = list(
            sample_rows[0].keys()
        )

        output = []

        output.append(
            f"Total Rows Returned: {len(rows)}"
        )

        output.append(
            f"Columns: {', '.join(headers)}"
        )

        output.append("")

        output.append(
            "Sample Records:"
        )

        output.append(
            SmartSerializer._table(
                sample_rows,
                max_rows
            )
        )

        return "\n".join(output)