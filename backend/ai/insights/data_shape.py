from enum import Enum


class DataShape(Enum):

    SINGLE_VALUE = "single_value"

    COMPARISON = "comparison"

    TREND = "trend"

    RANKED_LIST = "ranked_list"

    LARGE_SUMMARY = "large_summary"