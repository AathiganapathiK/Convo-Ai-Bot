"""
Offline fixture data and MockDimensionValueProvider.

This lives under test/ deliberately. None of these values exist in the
production semantic configuration and none of this module is importable by
production code paths - the resolver depends on the DimensionValueProvider
contract in semantic/value_provider.py, never on this file.

The fixture is adversarial on purpose. It contains exact values, prefix
extensions of those values, a near-misspelling, a token that lives in two
dimensions, and a value that is also a metric word - because those are the
shapes that produced every real failure we have seen.
"""
from semantic.value_provider import (
    PROVENANCE_MOCK,
    StaticDimensionValueProvider,
)


# The whole world, as far as offline tests are concerned.
FIXTURE_VALUES = {
    "City": [
        "CHENNAI",
        "MUMBAI",
        "COIMBATORE",
        "ELECTRONIC CITY",
    ],
    "District": [
        # Same token as City -> genuine cross-dimension ambiguity.
        "CHENNAI",
        "COIMBATORE",
    ],
    "Brand": [
        "RAMRAJ",
        "RAMRAJ PANT",
        "RAMRAJ SHIRT",
        "RAMRAJ DHOTI",
        # Same token as State -> genuine cross-dimension ambiguity.
        "VT",
    ],
    "State": [
        "VT",
        "TAMIL NADU",
    ],
    "Product": [
        "PANT",
        "SHIRT",
        "DHOTI",
    ],
    "Product Category": [
        "MENSWEAR",
    ],
    "Payment Status": [
        # Also a metric word ("Pending Amount"); exists to prove a metric
        # phrase offered as a value is handled by evidence, not by a blocklist.
        "PENDING",
    ],
}


class MockDimensionValueProvider(StaticDimensionValueProvider):
    """
    Fixture-backed provider used by every offline test.

    Identical in contract to DbDimensionValueProvider: same method signatures,
    same ValueCandidate shape, same provenance discipline. Only the source of
    the values differs, which is what lets the scoring and ambiguity tests be
    trusted as evidence about the real path.
    """

    def __init__(self, values_by_dimension=None):
        super().__init__(
            values_by_dimension=dict(values_by_dimension or FIXTURE_VALUES),
            provenance=PROVENANCE_MOCK,
        )
