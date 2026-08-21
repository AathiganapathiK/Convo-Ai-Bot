import pytest
from unittest.mock import patch, MagicMock
from semantic.matching.models import CachedDimensionValue, ResolutionStatus
from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.semantic_resolver import SemanticResolver
from services.conversation_memory import add_exchange, get_history, conversation_store


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


# Standard mock indexed values for our tests:
MOCK_INDEXED_VALUES = [
    make_cached_value(1, "City", "Locations", "City", "Coimbatore"),
    make_cached_value(2, "District", "Locations", "District", "Coimbatore"),
    make_cached_value(3, "Brand", "Products", "Brand", "Ramraj"),
    make_cached_value(4, "Prod Grp", "Products", "ProdGrp", "Ramraj"),
    make_cached_value(5, "City", "Locations", "City", "Chennai"),
]


@pytest.fixture(autouse=True)
def clean_memory():
    conversation_store.clear()
    yield
    conversation_store.clear()


@pytest.fixture
def mock_resolver_env():
    # Patch _fetch_active_metadata so we don't query a database
    # format:
    # metric_rows: metric_name, business_name, table_name, column_name, aggregation_type, synonyms
    mock_metrics = [
        ("Sales", "Sales", "SalesTable", "Amount", "SUM", ""),
        ("Outstanding", "Outstanding", "FinanceTable", "Due", "SUM", "")
    ]
    # dimension_rows: dimension_name, business_name, table_name, column_name, synonyms, semantic_category
    mock_dimensions = [
        ("City", "City", "Locations", "City", "", ""),
        ("District", "District", "Locations", "District", "", ""),
        ("Brand", "Brand", "Products", "Brand", "", "")
    ]

    with patch("semantic.semantic_resolver.SemanticResolver._fetch_active_metadata", return_value=(mock_metrics, mock_dimensions)), \
         patch("semantic.dimension_value_resolver.DimensionValueResolver._load_dimension_values", return_value=MOCK_INDEXED_VALUES):
        yield


# 1. Previous City + current ambiguous Coimbatore -> City / Coimbatore
def test_previous_city_coimbatore(mock_resolver_env):
    prev_context = {
        "metrics": [],
        "dimensions": [{"dimension_name": "City", "business_name": "City", "table_name": "Locations", "column_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "table_name": "Locations", "column_name": "City", "value": "Chennai", "normalized_value": "chennai"}]
    }

    res = SemanticResolver.resolve("conn_123", "Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is True
    assert res["followup_context"]["previous_dimension"] == "City"
    assert res["followup_context"]["current_value"] == "coimbatore"
    assert len(res["value_matches"]) == 1
    assert res["value_matches"][0]["business_name"] == "City"
    assert res["value_matches"][0]["value"] == "Coimbatore"


# 2. Previous Brand + current ambiguous value -> Brand candidate selected
def test_previous_brand_ramraj(mock_resolver_env):
    prev_context = {
        "metrics": [],
        "dimensions": [{"dimension_name": "Brand", "business_name": "Brand", "table_name": "Products", "column_name": "Brand"}],
        "resolved_values": []
    }

    res = SemanticResolver.resolve("conn_123", "Ramraj", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is True
    assert res["followup_context"]["previous_dimension"] == "Brand"
    assert len(res["value_matches"]) == 1
    assert res["value_matches"][0]["business_name"] == "Brand"
    assert res["value_matches"][0]["value"] == "Ramraj"


# 3. Previous dimension has no candidate for current value -> no forced selection
def test_previous_dimension_no_candidate(mock_resolver_env):
    prev_context = {
        "metrics": [],
        "dimensions": [{"dimension_name": "Brand", "business_name": "Brand", "table_name": "Products", "column_name": "Brand"}],
        "resolved_values": []
    }

    # "Coimbatore" matches City and District, but not Brand
    res = SemanticResolver.resolve("conn_123", "Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION"
    # Returns both candidates as ambiguous
    assert len(res["value_matches"]) == 2


# 4. No previous context -> normal ambiguity
def test_no_previous_context(mock_resolver_env):
    res = SemanticResolver.resolve("conn_123", "Coimbatore", previous_semantic_context=None)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "NO_ELIGIBLE_PREVIOUS_CONTEXT"
    assert len(res["value_matches"]) == 2


# 5. Previous context from STRONG_AMBIGUITY -> must not be used
def test_previous_strong_ambiguity_ignored(mock_resolver_env):
    # Previous turn had multiple value matches but they were not successfully resolved
    # Thus, no "dimensions" or "resolved_values" were registered (or they were empty)
    prev_context = {
        "metrics": [],
        "dimensions": [],
        "resolved_values": []
    }

    res = SemanticResolver.resolve("conn_123", "Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert len(res["value_matches"]) == 2


# 6. Current explicit dimension label -> B.1 wins over previous context
def test_explicit_dimension_label_wins(mock_resolver_env):
    prev_context = {
        "metrics": [],
        "dimensions": [{"dimension_name": "District", "business_name": "District", "table_name": "Locations", "column_name": "District"}],
        "resolved_values": []
    }

    # Query has explicit B.1 label "city"
    res = SemanticResolver.resolve("conn_123", "city Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "EXPLICIT_DIMENSION_LABEL_PRESENT"
    # B.1 filter resolves to City, overriding the previous District context
    assert len(res["value_matches"]) == 1
    assert res["value_matches"][0]["business_name"] == "City"


# 7. Current metric/topic shift -> previous context does not blindly apply
def test_metric_shift_prevents_inheritance(mock_resolver_env):
    prev_context = {
        "metrics": [{"metric_name": "Sales", "business_name": "Sales", "table_name": "SalesTable", "column_name": "Amount"}],
        "dimensions": [{"dimension_name": "City", "business_name": "City", "table_name": "Locations", "column_name": "City"}],
        "resolved_values": []
    }

    # Query introduces a new metric: "Outstanding" (which is a metric shift)
    res = SemanticResolver.resolve("conn_123", "outstanding Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "CURRENT_METRICS_PRESENT"
    assert len(res["value_matches"]) == 2


# 8. Current single-dimension value -> normal resolution, no unnecessary previous-context filtering
def test_single_dimension_value_no_filtering(mock_resolver_env):
    prev_context = {
        "metrics": [],
        "dimensions": [{"dimension_name": "Brand", "business_name": "Brand", "table_name": "Products", "column_name": "Brand"}],
        "resolved_values": []
    }

    # "Chennai" only matches City (not ambiguous)
    res = SemanticResolver.resolve("conn_123", "Chennai", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "SINGLE_DIMENSION_VALUE"
    assert len(res["value_matches"]) == 1
    assert res["value_matches"][0]["business_name"] == "City"


# 9. Previous context is from different conversation/session -> inaccessible
def test_different_session_isolation(mock_resolver_env):
    # Turn 1 in session "session_A"
    add_exchange("user_1", "show sales for Chennai", "SELECT ...", "session_A", semantic_context={
        "metrics": [],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Chennai"}]
    })

    # Retrieve history for "session_B"
    history_B = get_history("user_1", "session_B")
    assert len(history_B) == 0  # session B has no history


# 10. Previous context is from different employee/company -> inaccessible
def test_different_user_isolation(mock_resolver_env):
    # Turn 1 for "user_1"
    add_exchange("user_1", "show sales for Chennai", "SELECT ...", "session_123", semantic_context={
        "metrics": [],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Chennai"}]
    })

    # Retrieve history for "user_2"
    history_user_2 = get_history("user_2", "session_123")
    assert len(history_user_2) == 0  # user_2 has no access to user_1's session


# 11. Multiple previous turns exist -> only the latest valid semantic context should be considered
def test_multiple_turns_latest_valid(mock_resolver_env):
    # Turn 1: Valid City context
    add_exchange("user_1", "sales in Chennai", "SELECT ...", "session_1", semantic_context={
        "metrics": [],
        "dimensions": [{"dimension_name": "City", "business_name": "City"}],
        "resolved_values": [{"dimension_id": 1, "business_name": "City", "value": "Chennai"}]
    })

    # Turn 2: Invalid/Empty context (e.g. general query or ambiguity)
    add_exchange("user_1", "what about general?", "SELECT ...", "session_1", semantic_context=None)

    history = get_history("user_1", "session_1")
    assert len(history) == 2

    # Extract previous valid context helper
    previous_semantic_context = None
    for item in reversed(history):
        sem_ctx = item.get("semantic_context")
        if sem_ctx and isinstance(sem_ctx, dict):
            if sem_ctx.get("resolved_values") or sem_ctx.get("dimensions"):
                previous_semantic_context = sem_ctx
                break

    assert previous_semantic_context is not None
    assert previous_semantic_context["dimensions"][0]["business_name"] == "City"


# 12. Stale/invalid previous semantic context -> ignored
def test_stale_or_invalid_ignored(mock_resolver_env):
    # Context with no dimensions or resolved values
    prev_context = {
        "metrics": [{"metric_name": "Sales"}],
        "dimensions": [],
        "resolved_values": []
    }

    res = SemanticResolver.resolve("conn_123", "Coimbatore", previous_semantic_context=prev_context)
    assert res["followup_context"]["applied"] is False
    assert res["followup_context"]["reason"] == "NO_PREVIOUS_RESOLVED_DIMENSION"


# 13. Existing add_exchange callers without semantic_context -> continue working
def test_add_exchange_backward_compatible():
    # Calling add_exchange without the semantic_context parameter
    add_exchange("user_1", "plain question", "SELECT *", "session_1")
    history = get_history("user_1", "session_1")
    assert len(history) == 1
    assert "semantic_context" not in history[0]
    assert history[0]["question"] == "plain question"


# 14. Existing get_history behavior -> unchanged
def test_get_history_behavior():
    add_exchange("user_1", "q1", "sql1", "session_1")
    add_exchange("user_1", "q2", "sql2", "session_1")
    history = get_history("user_1", "session_1")
    assert len(history) == 2
    assert history[0]["question"] == "q1"
    assert history[1]["question"] == "q2"
