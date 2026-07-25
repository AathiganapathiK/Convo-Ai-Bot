from decimal import Decimal

# Centralized list of currency-related column names
CURRENCY_COLUMNS = {
    "sales",
    "totalsales",
    "revenue",
    "amount",
    "cost",
    "totalcost",
    "profit",
    "price",
    "unitprice",
    "discount",
    "discountamount",
    "margin",
    "target",
}


def is_currency_column(column_name: str) -> bool:
    """
    Determines whether a column represents a monetary value.
    """
    if not column_name:
        return False

    normalized = column_name.replace("_", "").replace(" ", "").lower()

    return normalized in CURRENCY_COLUMNS


def format_indian_currency(value):
    """
    Formats a numeric value using Indian currency grouping.

    Example:
        1500000 -> ₹15,00,000
        12345678.50 -> ₹1,23,45,678.50
    """
    if value is None:
        return value

    if not isinstance(value, (int, float, Decimal)):
        return value

    negative = value < 0
    value = abs(float(value))

    integer_part = int(value)
    decimal_part = round(value - integer_part, 2)

    integer_str = str(integer_part)

    if len(integer_str) > 3:
        last_three = integer_str[-3:]
        remaining = integer_str[:-3]

        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]

        if remaining:
            groups.insert(0, remaining)

        integer_str = ",".join(groups + [last_three])

    decimal_text = ""

    if decimal_part > 0:
        decimal_text = f"{decimal_part:.2f}"[1:]  # ".50"

    formatted = f"₹{integer_str}{decimal_text}"

    if negative:
        formatted = "-" + formatted

    return formatted

def format_value(column_name: str, value):
    """
    Formats a value based on its semantic meaning.
    """
    if is_currency_column(column_name):
        return format_indian_currency(value)

    return value