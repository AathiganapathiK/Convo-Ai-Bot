import pytest
from unittest.mock import patch, MagicMock
from semantic.matching.models import CachedDimensionValue
from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.semantic_resolver import SemanticResolver

def make_cached_value(dim_id, bus_name, tbl, col, val):
    val_norm = val.lower()
    val_tokens = val_norm.split()
    from semantic.matching.singular_plural_matcher import SingularPluralMatcher
    val_singulars = [SingularPluralMatcher._to_singular(t) for t in val_tokens]
    return CachedDimensionValue(
        semantic_dimension_id=dim_id,
        business_name=bus_name,
        table_name=tbl,
        column_name=col,
        value=val,
        normalized_value=val_norm,
        runtime_stored_norm=val_norm,
        runtime_stored_tokens=val_tokens,
        runtime_stored_singulars=val_singulars,
        runtime_raw_norm=val_norm,
        runtime_raw_tokens=val_tokens,
        runtime_raw_singulars=val_singulars
    )

MOCK_INDEXED_VALUES = [
    make_cached_value(1, "City", "Locations", "City", "Coimbatore"),
    make_cached_value(2, "District", "Locations", "District", "Coimbatore"),
    make_cached_value(3, "Brand", "Products", "Brand", "Ramraj"),
    make_cached_value(4, "Prod Grp", "Products", "ProdGrp", "Ramraj"),
    make_cached_value(5, "City", "Locations", "City", "Chennai"),
]

@pytest.fixture
def mock_resolver_env():
    # Mock metadata: Metrics: Qty, Amt, Sales
    mock_metrics = [
        ("Qty", "Qty", "SalesTable", "Quantity", "SUM", "quantity"),
        ("Amt", "Amt", "SalesTable", "Amount", "SUM", "amount"),
        ("Sales", "Sales", "SalesTable", "Sales", "SUM", "sales")
    ]
    mock_dimensions = [
        ("City", "City", "Locations", "City", "", ""),
        ("District", "District", "Locations", "District", "", ""),
        ("Brand", "Brand", "Products", "Brand", "", ""),
        ("Prod Grp", "Prod Grp", "Products", "ProdGrp", "", "")
    ]

    with patch("semantic.semantic_resolver.SemanticResolver._fetch_active_metadata", return_value=(mock_metrics, mock_dimensions)), \
         patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values", return_value=MOCK_INDEXED_VALUES):
        yield

# TEST 1 — SAME METRIC
def test_same_metric(mock_resolver_env):
    prev_context = {
        "metrics": [{"metric_name": "Qty", "business_name": "Qty"}],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Coimbatore", "normalized_value": "coimbatore"}]
    }

    # Query restates the same metric "qty"
    res = SemanticResolver.resolve("conn_123", "qty Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is True
    assert res["followup_context"]["reason"] == "PREVIOUS_DIMENSION_MATCH"
    assert len(res["value_matches"]) == 1
    assert res["value_matches"][0]["business_name"] == "City"

# TEST 2 — DIFFERENT METRIC (Shift)
def test_different_metric(mock_resolver_env):
    prev_context = {
        "metrics": [{"metric_name": "Qty", "business_name": "Qty"}],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Coimbatore", "normalized_value": "coimbatore"}]
    }

    # Query introduces a new, conflicting metric "amt"
    res = SemanticResolver.resolve("conn_123", "amt Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "CURRENT_METRICS_PRESENT"
    # Ambiguous matches should remain unfiltered (both City and District)
    assert len(res["value_matches"]) == 2
    assert {v["business_name"] for v in res["value_matches"]} == {"City", "District"}

# TEST 3 — NO CURRENT METRIC
def test_no_current_metric(mock_resolver_env):
    prev_context = {
        "metrics": [{"metric_name": "Qty", "business_name": "Qty"}],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Coimbatore", "normalized_value": "coimbatore"}]
    }

    # Query has no metric
    res = SemanticResolver.resolve("conn_123", "Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is True
    assert res["followup_context"]["reason"] == "PREVIOUS_DIMENSION_MATCH"
    assert len(res["value_matches"]) == 1
    assert res["value_matches"][0]["business_name"] == "City"

# TEST 4 — METRIC SUBSET
def test_metric_subset(mock_resolver_env):
    prev_context = {
        "metrics": [
            {"metric_name": "Qty", "business_name": "Qty"},
            {"metric_name": "Sales", "business_name": "Sales"}
        ],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Coimbatore", "normalized_value": "coimbatore"}]
    }

    # Query metric "qty" is a subset of previous metrics [Qty, Sales]
    res = SemanticResolver.resolve("conn_123", "qty Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is True
    assert res["followup_context"]["reason"] == "PREVIOUS_DIMENSION_MATCH"
    assert len(res["value_matches"]) == 1
    assert res["value_matches"][0]["business_name"] == "City"

# TEST 5 — NEW ADDITIONAL METRIC
def test_new_additional_metric(mock_resolver_env):
    prev_context = {
        "metrics": [{"metric_name": "Qty", "business_name": "Qty"}],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Coimbatore", "normalized_value": "coimbatore"}]
    }

    # Query contains [Qty, Amt] - "Amt" is a new additional metric not present in previous context
    res = SemanticResolver.resolve("conn_123", "qty amt Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "CURRENT_METRICS_PRESENT"

# TEST 6 — EXPLICIT DIMENSION OVERRIDE
def test_explicit_dimension_override(mock_resolver_env):
    prev_context = {
        "metrics": [],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Chennai", "normalized_value": "chennai"}]
    }

    # Query specifies explicit label "district"
    res = SemanticResolver.resolve("conn_123", "district Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "EXPLICIT_DIMENSION_LABEL_PRESENT"
    assert len(res["value_matches"]) == 1
    assert res["value_matches"][0]["business_name"] == "District"

# TEST 7 — MULTIPLE VALUES
def test_multiple_values(mock_resolver_env):
    prev_context = {
        "metrics": [{"metric_name": "Qty", "business_name": "Qty"}],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Coimbatore", "normalized_value": "coimbatore"}]
    }

    # Query has multiple values (Chennai, Coimbatore)
    res = SemanticResolver.resolve("conn_123", "qty Chennai and Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "MULTIPLE_TARGET_VALUES"
