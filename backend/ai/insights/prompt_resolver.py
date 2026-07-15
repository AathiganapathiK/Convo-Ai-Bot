from ai.insights.data_shape import DataShape

from ai.insights.prompt_templates import (
    SINGLE_VALUE_TEMPLATE,
    COMPARISON_TEMPLATE,
    TREND_TEMPLATE,
    RANKED_LIST_TEMPLATE,
    LARGE_SUMMARY_TEMPLATE
)


class PromptResolver:

    @staticmethod
    def get_template(shape):

        if shape == DataShape.SINGLE_VALUE:
            return SINGLE_VALUE_TEMPLATE

        if shape == DataShape.COMPARISON:
            return COMPARISON_TEMPLATE

        if shape == DataShape.TREND:
            return TREND_TEMPLATE

        if shape == DataShape.RANKED_LIST:
            return RANKED_LIST_TEMPLATE

        return LARGE_SUMMARY_TEMPLATE