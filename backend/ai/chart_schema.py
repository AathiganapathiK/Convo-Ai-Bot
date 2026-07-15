from pydantic import BaseModel
from typing import List
from typing import Optional


class ChartAnalysis(BaseModel):
    row_count: int
    column_count: int
    date_columns: List[str]
    numeric_columns: List[str]
    category_columns: List[str]
    measure_count: int
    large_dataset: Optional[bool] = False
    chart_warning: Optional[str] = None
    top_n_applied: Optional[bool] = False
    others_bucket: Optional[bool] = False
    category_count: Optional[int] = 0
    long_labels: Optional[bool] = False
    sampling_required: Optional[bool] = False
    pie_recommended: Optional[bool] = False
    too_many_measures: Optional[bool] = False
    outliers_detected: Optional[bool] = False
    outlier_count: Optional[int] = 0
    outlier_method: Optional[str] = "iqr"


class ChartMetadata(BaseModel):
    recommended_view: str
    available_views: List[str]
    x_axis: str
    y_axis: str
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None
    measures: Optional[List[str]] = None
    layout: Optional[str] = None
    title: str
    insight: Optional[str] = None
    analysis: ChartAnalysis

def validate_chart_schema(chart):

    try:
        validated = ChartMetadata(
            **chart
        )
        return validated.model_dump()

    except Exception as e:
        print(
            "Chart schema validation failed:",
            e
        )
        return None