import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.matching.stopwords import STOPWORDS
from semantic.matching.candidate_phrase_extractor import CandidatePhraseExtractor
from semantic.matching.fuzzy_matcher import FuzzyMatcher
from semantic.matching.models import MatchingContext, QuestionContext, CachedDimensionValue
from semantic.matching.confidence import MatchSettings
from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching.singular_plural_matcher import SingularPluralMatcher
from rapidfuzz import fuzz

def run_stopword_audit():
    questions = [
        "show sales",
        "total sales",
        "show monthly sales",
        "sales by region",
        "sales by product",
        "show sales for tamil nadu",
        "show total sales for cotton pants",
        "compare sales by month"
    ]
    
    print("=== STOPWORD AUDIT ===")
    extractor = CandidatePhraseExtractor()
    
    # We mock a small database with region/product/cotton pants/tamil nadu values to see what the resolver resolves
    mock_db = [
        "Tamil Nadu",
        "Cotton Pants",
        "South Region",
        "North Region",
        "Shirts"
    ]
    indexed_values = []
    for idx, val in enumerate(mock_db):
        norm_val = DimensionValueResolver._normalize_text(val)
        val_tokens = norm_val.split()
        val_singulars = [SingularPluralMatcher._to_singular(t) for t in val_tokens]
        indexed_values.append(CachedDimensionValue(
            semantic_dimension_id=idx + 1,
            business_name="Dimension",
            table_name="mock_table",
            column_name="mock_col",
            value=val,
            normalized_value=norm_val,
            runtime_stored_norm=norm_val,
            runtime_stored_tokens=val_tokens,
            runtime_stored_singulars=val_singulars,
            runtime_raw_norm=norm_val,
            runtime_raw_tokens=val_tokens,
            runtime_raw_singulars=val_singulars
        ))
        
    import unittest.mock as mock
    mock_conn = mock.MagicMock()
    mock_engine = mock.patch("semantic.dimension_value_resolver.engine").start()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    
    # Return mock rows that represent our indexed values
    mock_rows = []
    for val in indexed_values:
        mock_rows.append(mock.MagicMock(_mapping={
            "semantic_dimension_id": val.semantic_dimension_id,
            "business_name": val.business_name,
            "table_name": val.table_name,
            "column_name": val.column_name,
            "value": val.value,
            "normalized_value": val.normalized_value
        }))
    mock_conn.execute.return_value.fetchall.return_value = mock_rows

    for q in questions:
        norm = DimensionValueResolver._normalize_text(q)
        tokens = norm.split()
        removed = [t for t in tokens if t in STOPWORDS]
        phrases = extractor.extract(q)
        sales_survives = "sales" in [p.split() for p in phrases] or "sales" in phrases
        
        # Call full resolver
        resolved = DimensionValueResolver.resolve("mock_conn", q)
        resolved_vals = [r["value"] for r in resolved]
        
        print(f"Original: {q!r}")
        print(f"  Normalized: {norm!r}")
        print(f"  Removed Stopwords: {removed}")
        print(f"  Candidate Phrases: {phrases}")
        print(f"  'sales' survives in candidate phrases? {sales_survives}")
        print(f"  Resolved Dimension Values: {resolved_vals}")
        print()
    mock.patch.stopall()

def run_threshold_audit():
    print("=== EMPIRICAL THRESHOLD AUDIT ===")
    
    # 1. Main representative mock values
    main_values = [
        "Pants",
        "Cotton Pants",
        "Formal Pants",
        "Children Pants",
        "Shirts",
        "Formal Shirts",
        "T-Shirts",
        "Cotton Shirts",
        "Banians",
        "Children's Wear",
        "Men's Wear",
        "Women's Wear",
        "People Choice"
    ]
    
    # 2. Large set of realistic distractors / other terms
    distractors = [
        "Invoices",
        "Purchase Orders",
        "Vendors",
        "Suppliers",
        "Customers",
        "Employees",
        "Transactions",
        "Payments",
        "Receipts",
        "Refunds",
        "Accounts",
        "Ledgers",
        "Budgets",
        "Forecasts",
        "Inventory",
        "Stock",
        "Warehouses",
        "Locations",
        "Divisions",
        "Branches",
        "Departments",
        "Managers",
        "Executives",
        "Sales Representatives",
        "Targets",
        "Quotas",
        "Commissions",
        "Discounts",
        "Coupons",
        "Tax Rates",
        "GST",
        "VAT",
        "Shipping Address",
        "Billing Address",
        "Cities",
        "States",
        "Countries",
        "Regions",
        "Zones",
        "Districts",
        "Postal Codes",
        "Phone Numbers",
        "Email Addresses",
        "User Roles",
        "Permissions",
        "Audit Logs",
        "Session IDs",
        "System Settings",
        "App Version",
        "Date Range"
    ]
    
    all_indexed = main_values + distractors
    normalized_indexed = [DimensionValueResolver._normalize_text(v) for v in all_indexed]
    
    positive_cases = [
        ("cottn pant", "Cotton Pants"),
        ("forml shirt", "Formal Shirts"),
        ("childern wear", "Children's Wear"),
        ("womens wear", "Women's Wear"),
        ("mens wear", "Men's Wear"),
        ("persn choice", "People Choice"),
        ("child wear", "Children's Wear")
    ]
    
    negative_cases = [
        "laptop",
        "banana",
        "hospital",
        "customer",
        "invoice",
        "employee",
        "computer",
        "mobile",
        "furniture",
        "payment"
    ]
    
    ambiguous_cases = [
        "pant",
        "shirt",
        "wear",
        "men",
        "cotton"
    ]
    
    print("\n--- POSITIVE CASES SCORING ---")
    pos_scores = []
    for q, expected in positive_cases:
        # Generate phrases
        phrases = CandidatePhraseExtractor().extract(q)
        best_score = 0
        best_match = None
        best_phrase = None
        for phrase in phrases:
            for val in all_indexed:
                norm_val = DimensionValueResolver._normalize_text(val)
                score = fuzz.WRatio(phrase, norm_val)
                if score > best_score:
                    best_score = score
                    best_match = val
                    best_phrase = phrase
        print(f"Query: {q!r} (Expected: {expected!r}) -> Best Match: {best_match!r} | Score: {best_score:.1f} | Phrase: {best_phrase!r}")
        if best_match == expected:
            pos_scores.append(best_score)
        else:
            # If the best match was not expected, record it to see if it's a false positive or mismatch
            print(f"  [MISMATCH] Expected {expected!r} but got {best_match!r} with score {best_score:.1f}")
            # If the expected value was also matched, report its score
            exp_score = 0
            for phrase in phrases:
                score = fuzz.WRatio(phrase, DimensionValueResolver._normalize_text(expected))
                if score > exp_score:
                    exp_score = score
            print(f"  Expected {expected!r} scored: {exp_score:.1f}")
            pos_scores.append(exp_score)
            
    print("\n--- NEGATIVE CASES SCORING ---")
    neg_scores = []
    for q in negative_cases:
        phrases = CandidatePhraseExtractor().extract(q)
        best_score = 0
        best_match = None
        for phrase in phrases:
            for val in all_indexed:
                norm_val = DimensionValueResolver._normalize_text(val)
                score = fuzz.WRatio(phrase, norm_val)
                if score > best_score:
                    best_score = score
                    best_match = val
        print(f"Query: {q!r} -> Best Distractor Match: {best_match!r} | Score: {best_score:.1f}")
        neg_scores.append(best_score)
        
    print("\n--- AMBIGUOUS CASES SCORING ---")
    for q in ambiguous_cases:
        phrases = CandidatePhraseExtractor().extract(q)
        print(f"Query: {q!r}")
        matches_above_75 = []
        for phrase in phrases:
            for val in all_indexed:
                norm_val = DimensionValueResolver._normalize_text(val)
                score = fuzz.WRatio(phrase, norm_val)
                if score >= 75:
                    matches_above_75.append((val, score))
        # Sort and deduplicate
        matches_above_75 = sorted(list(set(matches_above_75)), key=lambda x: -x[1])
        for val, score in matches_above_75[:5]:
            print(f"  Candidate: {val!r} | Score: {score:.1f}")
            
    min_pos = min(pos_scores)
    max_neg = max(neg_scores)
    gap = min_pos - max_neg
    print(f"\n--- THRESHOLD METRICS ---")
    print(f"Lowest Valid-Positive Score: {min_pos:.1f}")
    print(f"Highest Negative/Distractor Score: {max_neg:.1f}")
    print(f"Score Gap: {gap:.1f}")

if __name__ == "__main__":
    run_stopword_audit()
    run_threshold_audit()
