from ai.chart_schema import validate_chart_schema
from decimal import Decimal
import json
import statistics
import webbrowser

PIE_MAX_CATEGORIES = 15
BAR_MAX_CATEGORIES = 25

TABLE_WARNING_ROWS = 500

DIMENSION_COLUMNS = {
    "productkey",
    "resellerkey",
    "employeekey",
    "salesterritorykey",
    "employeeid"
}

MEASURE_PRIORITY = [
    "sales",
    "totalsales",
    "cost",
    "totalcost",
    "quantity",
    "unitprice",
    "target"
]

VALID_CHART_TYPES = {
    "table",
    "bar",
    "line",
    "pie",
    "scatter"
}

DIMENSION_PRIORITY = [
    "product",
    "region",
    "salesperson",
    "reseller",
    "category",
    "subcategory"
]

def generate_chart_metadata(question, rows):

    if not rows:
        return None

    columns = list(rows[0].keys())

    if len(columns) < 2:
        return None

    chart = None
    chart_rows = rows

    date_columns = []
    numeric_columns = []
    category_columns = []

    for col in columns:

        sample = rows[0].get(col)

        if sample is None:
            continue

        col_lower = col.lower()

        if (
            "date" in col_lower
            or "month" in col_lower
            or "year" in col_lower
        ):
            date_columns.append(col)

        elif isinstance(
            sample,
            (int, float, Decimal)
        ):

            if col_lower in DIMENSION_COLUMNS:
                category_columns.append(col)
            else:
                numeric_columns.append(col)

        else:
            category_columns.append(col)

    best_measure = get_best_measure(numeric_columns)

    outlier_count = 0
    outliers_detected = False

    if best_measure:
        outlier_count = detect_outliers(
            rows,
            best_measure
        )
        outliers_detected = outlier_count > 0

    best_dimension = get_best_dimension(
        category_columns
    )



    analysis = {
        "row_count": len(rows),
        "column_count": len(columns),

        "date_columns": date_columns,
        "numeric_columns": numeric_columns,
        "category_columns": category_columns,

        "measure_count": len(numeric_columns),
        "top_n_applied": False,
        "others_bucket": False,
        "large_dataset": False,

        "chart_warning": None,
        "category_count": 0,
        "long_labels": False,
        "sampling_required": False,
        "pie_recommended": False,
        "too_many_measures": False,

        "outliers_detected": outliers_detected,
        "outlier_count": outlier_count,
        "outlier_method": "iqr",
    }

    analysis["too_many_measures"] = (
        len(numeric_columns) > 4
    )

    if len(rows) > TABLE_WARNING_ROWS:
        if len(rows) > 2000:
            analysis["sampling_required"] = True

        analysis["large_dataset"] = True

        analysis["chart_warning"] = (
            f"Large dataset detected "
            f"({len(rows)} rows)"
        )


    # -------------------------
    # Time Series
    # -------------------------

    if date_columns and numeric_columns:

        available_views = [
            "table",
            "line",
            "bar"
        ]

        analysis["multi_measure"] = (
            len(numeric_columns) > 1
        )

        chart = {
            "recommended_view": "line",
            "available_views": available_views,
            "x_axis": date_columns[0],
            "y_axis": best_measure,
            "measures": numeric_columns,
            "title": f"{best_measure} Trend",
            "analysis": analysis
        }


        return validate_chart_metadata(
            chart,
            rows
        )


    # -------------------------
    # Correlation Analysis
    # -------------------------

    if (
        len(numeric_columns) >= 2
        and not category_columns
        and not date_columns
    ):

        chart = {
            "recommended_view": "scatter",

            "available_views": [
                "table",
                "scatter"
            ],

            "x_axis":
                numeric_columns[0],

            "y_axis":
                numeric_columns[1],

            "title":
                f"{numeric_columns[1]} vs {numeric_columns[0]}",

            "analysis":
                analysis
        }
        return validate_chart_metadata(
            chart,
            rows
        )

    # -------------------------
    # Category Comparison
    # -------------------------

    if category_columns and numeric_columns:

        available_views = [
            "table",
            "bar"
        ]

        unique_categories = len(
            set(
                str(
                    row.get(
                        best_dimension
                    )
                )
                for row in rows
            )
        )
        analysis["category_count"] = (
    unique_categories
)

        if category_columns:

            max_label_length = max(
                len(
                    str(
                        row.get(
                    category_columns[0],
                    ""
                )
            )
        )
        for row in rows[:20]
    )

            analysis["long_labels"] = (
                max_label_length > 20
            )


        if unique_categories > BAR_MAX_CATEGORIES:

            chart_rows, top_n_used = (
                apply_top_n(
                    rows,
                    best_dimension,
                    best_measure
                )
            )

        chart_rows = rows

        if unique_categories > PIE_MAX_CATEGORIES:

            chart_rows, top_n_used = (
                apply_top_n(
                    rows,
                    best_dimension,
                    best_measure
                )
            )

            analysis[
                "top_n_applied"
            ] = top_n_used

            analysis[
                "others_bucket"
            ] = top_n_used
        else:
            chart_rows = rows

        analysis["pie_recommended"] = (
            unique_categories <= PIE_MAX_CATEGORIES
        )

        if unique_categories <= PIE_MAX_CATEGORIES:
            available_views.append("pie")



        chart = {
            "recommended_view": "bar",
            "layout": (
                "horizontal"
                if unique_categories >= 6
                else "vertical"
            ),
            "available_views": available_views,
            "x_axis": best_dimension,
            "y_axis": best_measure,
            "title": f"{best_measure} by {best_dimension}",
            "analysis": analysis
        }

        if chart is None:

            return {
                "recommended_view": "table",
                "available_views": ["table"],
                "title": "Tabular Results",
                "analysis": analysis
            }, rows

        return (
            validate_chart_metadata(
                chart,
                rows
            ),
            chart_rows
        )
    
def get_best_measure(numeric_columns):

    for preferred in MEASURE_PRIORITY:

        for col in numeric_columns:

            if col.lower() == preferred:
                return col

    return numeric_columns[0] if numeric_columns else None

def validate_chart_metadata(chart, rows):

    if not chart:
        return None

    if not rows:
        return None

    chart["insight"] = (
        f"{chart.get('y_axis')} visualized by {chart.get('x_axis')}"
    )

    columns = set(rows[0].keys())

    x_axis = chart.get("x_axis")
    y_axis = chart.get("y_axis")

    if x_axis is None or y_axis is None:
        return validate_chart_schema(chart)

    if x_axis not in columns:
        return None

    if y_axis not in columns:
        return None

    available_views = chart.get(
        "available_views",
        []
    )

    valid_views = [
        view
        for view in available_views
        if view in VALID_CHART_TYPES
    ]

    chart["available_views"] = valid_views

    if (
        chart["recommended_view"]
        not in valid_views
    ):
        chart["recommended_view"] = (
            valid_views[0]
            if valid_views
            else "table"
        )
    return validate_chart_schema(
        chart
    )

def apply_top_n(
    rows,
    category_col,
    measure_col,
    top_n=10
):

    if len(rows) <= top_n:
        return rows, False

    sorted_rows = sorted(
        rows,
        key=lambda x: float(
            x.get(measure_col, 0)
        ),
        reverse=True
    )

    top_rows = sorted_rows[:top_n]

    remaining_rows = sorted_rows[top_n:]

    others_value = sum(
        float(
            row.get(
                measure_col,
                0
            )
        )
        for row in remaining_rows
    )

    others_row = {
        category_col: "Others",
        measure_col: others_value
    }

    top_rows.append(
        others_row
    )

    return top_rows, True


def get_best_dimension(
    category_columns
):

    for preferred in DIMENSION_PRIORITY:

        for col in category_columns:

            if col.lower() == preferred:
                return col

    return (
        category_columns[0]
        if category_columns
        else None
    )
    
def generate_kpis(rows):

    if not rows:
        return []

    row = rows[0]

    numeric_columns = []

    for column, value in row.items():

        if isinstance(
            value,
            (int, float, Decimal)
        ):
            numeric_columns.append(
                (column, value)
            )

    if not numeric_columns:
        return []

    # KPI-only query
    if len(rows) == 1:

        return [
            {
                "label": column,
                "value": float(value)
            }
            for column, value
            in numeric_columns
        ]

    return []


    
def detect_outliers(
    rows,
    measure
):

    values = []

    for row in rows:

        value = row.get(measure)

        if isinstance(
            value,
            (int, float, Decimal)
        ):
            values.append(
                float(value)
            )

    if len(values) < 10:
        return 0

    values.sort()

    q1_index = int(
        len(values) * 0.25
    )

    q3_index = int(
        len(values) * 0.75
    )

    q1 = values[q1_index]

    q3 = values[q3_index]

    iqr = q3 - q1

    lower_bound = (
        q1 - (1.5 * iqr)
    )

    upper_bound = (
        q3 + (1.5 * iqr)
    )

    outlier_count = sum(
        1
        for value in values
        if (
            value < lower_bound
            or value > upper_bound
        )
    )

    return outlier_count


def prettify_label(text):

    return (
        text
        .replace("_", " ")
        .replace("Total", "")
        .strip()
    )