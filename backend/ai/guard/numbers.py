"""
Gate 6 Step 33 - deterministic extraction of numeric claims from text.

WHY THIS IS NOT SIMPLE STRING MATCHING
    The application formats values before showing them to the model.
    utils/value_formatter.format_value() turns 1000000 into the Indian
    grouping "Rs10,00,000" for currency columns, so an answer quoting
    "10,00,000" is echoing what it was shown, not inventing anything. Comparing
    the answer's text against raw database values would reject correct answers.

    So numbers are parsed to a Decimal and compared numerically. Separators,
    currency symbols and scale words are removed as part of parsing, never
    matched as text.

NO TOLERANCE
    Comparison is exact after normalisation. "1M" matches 1000000; "1.2M" does
    not. A tolerance band wide enough to accept "approximately 1 million" for
    1,043,221 would also accept "1.1M" for 1,000,000, which is the exact class
    of error this exists to catch.

WHAT IS DELIBERATELY NOT TREATED AS A FINANCIAL CLAIM
    Years, fiscal-year spans and ISO dates. An answer saying "in FY 2024-25"
    is naming a period, not quoting a figure, and treating 2024 as an
    unsupported number would fire on almost every correct answer.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


# Scale words, mapped to their multiplier. Indian units are included because
# the application formats currency in Indian grouping and answers written for
# this business commonly use them.
SCALE_FACTORS = {
    "k": Decimal(1_000),
    "thousand": Decimal(1_000),
    "m": Decimal(1_000_000),
    "mn": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "b": Decimal(1_000_000_000),
    "bn": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
    "lakh": Decimal(100_000),
    "lakhs": Decimal(100_000),
    "crore": Decimal(10_000_000),
    "crores": Decimal(10_000_000),
}

_SCALE_PATTERN = "|".join(sorted(SCALE_FACTORS, key=len, reverse=True))

# A fiscal span (2024-25, 2024/2025) or an ISO date. Matched first so their
# digits are never read as figures.
# Full dates are listed before fiscal spans deliberately: alternation is
# ordered, and the fiscal pattern would otherwise consume "2025-04" out of
# "2025-04-01" and leave "01" behind to be read as a figure.
_PERIOD_PATTERN = re.compile(
    r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b"
    r"|\b\d{1,2}[-/]\d{1,2}[-/](?:19|20)\d{2}\b"
    r"|\b(?:19|20)\d{2}\s*[-/]\s*\d{2,4}\b",
    re.IGNORECASE,
)

_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")

# A number, optionally preceded by a currency symbol and optionally followed by
# a scale word or a percent sign. Digit grouping may be Western (1,000,000) or
# Indian (10,00,000) - both are handled by removing separators.
_NUMBER_PATTERN = re.compile(
    # A minus sign counts only when it is not joining two values, so the
    # hyphen in a range or an identifier is not read as a negative.
    r"(?P<sign>(?<![\w\d])-\s*)?"
    r"(?P<currency>[₹$€£]\s*)?"
    # Digits joined to letters are a label, not a figure: Q1, H2, FY25, A4.
    # Without this the "1" in "Q1" was read as an unsupported business number
    # and rejected a correct answer.
    r"(?<![A-Za-z0-9])"
    r"(?P<number>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    # The number must not be cut short in front of more digits. A trailing
    # full stop is a sentence ending, not part of the number, so it is allowed
    # here - without this, "sales were 1,000,000." parsed as 1,000.
    r"(?!\d)"
    # A scale word is optional and must end on a word boundary, so the "m" in
    # "1 method" is not read as "million". % stands alone.
    r"(?:\s*(?P<scale>%|(?:" + _SCALE_PATTERN + r")\b))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NumericClaim:
    """One number as it appears in a piece of text."""

    raw: str
    value: Decimal
    is_percentage: bool = False
    has_currency: bool = False
    has_scale: bool = False
    start: int = 0

    @property
    def is_bare_year(self) -> bool:
        """
        A four-digit integer in a plausible year range, written without a
        currency symbol, scale word, decimal or separator.
        """

        if self.is_percentage or self.has_currency or self.has_scale:
            return False

        if "." in self.raw or "," in self.raw:
            return False

        try:
            as_int = int(self.value)
        except (ValueError, InvalidOperation):
            return False

        return as_int == self.value and 1900 <= as_int <= 2100


def parse_number(text) -> Decimal | None:
    """
    Parse a single formatted value into a Decimal.

    Handles what format_value() produces - a currency symbol and either
    grouping convention - plus plain numbers and numeric types.
    """

    if text is None:
        return None

    if isinstance(text, bool):
        return None

    if isinstance(text, (int, float, Decimal)):
        try:
            return Decimal(str(text))
        except InvalidOperation:
            return None

    cleaned = str(text).strip()

    if not cleaned:
        return None

    negative = cleaned.startswith("-")

    for symbol in ("₹", "$", "€", "£", ",", "-", " "):
        cleaned = cleaned.replace(symbol, "")

    if not cleaned:
        return None

    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None

    return -value if negative else value


def extract_numeric_claims(text: str) -> list:
    """
    Every number stated in the text, with what it was written as.

    Period expressions are located first and their spans excluded, so the
    digits inside "FY 2024-25" or "2025-04-01" are never returned as figures.
    """

    if not text:
        return []

    excluded = [m.span() for m in _PERIOD_PATTERN.finditer(text)]

    def inside_period(start: int, end: int) -> bool:
        return any(s <= start and end <= e for s, e in excluded)

    claims = []

    for match in _NUMBER_PATTERN.finditer(text):
        if inside_period(match.start(), match.end()):
            continue

        digits = match.group("number")
        scale = (match.group("scale") or "").lower()

        value = parse_number(digits)

        if value is None:
            continue

        is_percentage = scale == "%"

        if scale and not is_percentage:
            value = value * SCALE_FACTORS[scale]

        if match.group("sign"):
            value = -value

        claims.append(
            NumericClaim(
                raw=match.group(0).strip(),
                value=value,
                is_percentage=is_percentage,
                has_currency=bool(match.group("currency")),
                has_scale=bool(scale) and not is_percentage,
                start=match.start(),
            )
        )

    return claims


def extract_years(text: str) -> set:
    """
    Every four-digit year mentioned, including both sides of a fiscal span.

    "FY 2024-25" yields {2024, 2025} - the second half is a two-digit
    abbreviation of the following year, which is how fiscal years are written
    in this business.
    """

    if not text:
        return set()

    years = set()

    for match in _PERIOD_PATTERN.finditer(text):
        span = match.group(0)

        found = _YEAR_PATTERN.findall(span)

        for year in found:
            years.add(int(year))

        # "2024-25" - expand the abbreviated second half.
        short = re.match(
            r"^((?:19|20)\d{2})\s*[-/]\s*(\d{2})$",
            span.strip(),
        )

        if short:
            century = int(short.group(1)) // 100
            years.add(century * 100 + int(short.group(2)))

    for match in _YEAR_PATTERN.finditer(text):
        years.add(int(match.group(0)))

    return years
