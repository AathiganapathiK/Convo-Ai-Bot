import sys
import os

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching import (
    MatchType,
    QuestionContext,
    MatchingContext,
    ExactMatcher,
    NormalizedMatcher,
    SingularPluralMatcher,
    FuzzyMatcher,
    STOPWORDS,
    QuestionSanitizer,
    MatchingPipeline
)
from semantic.matching.models import CachedDimensionValue

SETTINGS = {"FUZZY_SCORE_CUTOFF": 85}

# Helper to build cached values
def make_val(value):
    norm = value.lower()
    return CachedDimensionValue(
        semantic_dimension_id=1,
        business_name="MockDim",
        table_name="MockTable",
        column_name="MockCol",
        value=value,
        normalized_value=norm,
        runtime_stored_norm=norm,
        runtime_stored_tokens=norm.split(),
        runtime_stored_singulars=[SingularPluralMatcher._to_singular(t) for t in norm.split()],
        runtime_raw_norm=norm,
        runtime_raw_tokens=norm.split(),
        runtime_raw_singulars=[SingularPluralMatcher._to_singular(t) for t in norm.split()]
    )

# Raw values mirroring the DB index
RAW_VALUES = [
    # For "t"
    "TN4-CHN-T", "TN4-CHN-T", "T RAMANATHAPURAM", "T.N.PALAYAM", "T.NAGAR",
    "T.NARASAPURAM", "T.NARASIPURA", "T.PALUR", "T.RAMANATHAPURAM",
    "A--T-SHIRT", "EXPERT TERRA.T TRACK", "LITTLE STAR-T (2PCS)", "UNIFORM T SHIRT",
    
    # For "r"
    "AP16-VSKP-R", "AP16-VSKP-R", "KA19-MYS-R", "KA19-MYS-R", "TS24_WGL-R", "TS24_WGL-R",
    "M.G.R.NAGAR", "R.S.MANGALAM", "S R PURAM", "UNIBRO R.N PLAIN", "UNIBRO R.N PLAIN(W)",
    "UNIBRO R.NECK SAVER PACK", "UNIBRO R.NECK VALUE PACK",
    
    # For "m"
    "M.C.ROAD", "M.G.R.NAGAR", "M.KUNNATHUR", "M--MASK", "AIR MODAL M.TRUNK", "BAHAMA D.M STP",
    
    # For "ap"
    "AP-F", "AP-F", "GRN-AP", "ACC-Exp-Corp-AP", "ACC-Franchise-AP", "ACC-Marketing-AP",
    "ACC-Showroom-AP", "AKG-Franchise-AP", "AKG-Marketing-AP", "AKG-Showroom-AP",
    "ATC-Exp-Corp-AP", "ATC-Franchise-AP", "ATC-General-AP", "ATC-Marketing-AP",
    "ATC-Showroom-AP", "BandB-Marketing-AP", "BandB-Showroom-AP", "RHL-Exp-Corp-AP",
    "RHL-Franchise-AP", "RHL-General-AP", "RHL-Marketing-AP", "RHL-Showroom-AP",
    "RRF-Exp-Corp-AP", "RRF-Franchise-AP", "RRF-Marketing-AP", "RR-Franchise-AP",
    "RRF-Showroom-AP", "RR-Marketing-AP", "RR-Showroom-AP", "TARA-Franchise-AP",
    "TARA-Marketing-AP", "TARA-Showroom-AP", "VGS-General-AP", "VGS-Marketing-AP",
    "VGS-Showroom-AP", "VT-Franchise-AP", "VT-Marketing-AP", "VT-Showroom-AP",
    "AP", "AP", "AP", "AP", "AP", "AP", "AP", "AP",  # 8 copies of AP
    
    # For "ts"
    "TS-F", "TS-F", "COM-TS", "GRN-TS", "ACC-Exp-Corp-TS", "ACC-Franchise-TS", "ACC-Marketing-TS",
    "ACC-Showroom-TS", "AKG-Franchise-TS", "AKG-Marketing-TS", "AKG-Showroom-TS",
    "ATC-Exp-Corp-TS", "ATC-Franchise-TS", "ATC-Marketing-TS", "ATC-Showroom-TS",
    "BandB-Marketing-TS", "BandB-Showroom-TS", "RHL-Exp-Corp-TS", "RHL-Franchise-TS",
    "RHL-General-TS", "RHL-Marketing-TS", "RHL-Showroom-TS", "RRF-Franchise-TS",
    "RRF-Marketing-TS", "RR-Franchise-TS", "RRF-Showroom-TS", "RR-Marketing-TS",
    "RR-Showroom-TS", "TARA-Franchise-TS", "TARA-Showroom-TS", "VGS-Marketing-TS",
    "VT-Franchise-TS", "VT-Marketing-TS", "VT-Showroom-TS",
    "TS", "TS", "TS", "TS", "TS", "TS", "TS", "TS",  # 8 copies of TS
    
    # For "pants" / "pant"
    "LINEN PANT", "RAMRAJ PANT", "FORMAL PANTS",
    
    # For "banian" / "banians"
    "Banian", "Banians"
]

INDEXED_VALUES = [make_val(v) for v in RAW_VALUES]

QUERIES = [
    "t", "r", "m", "ap", "ts", "pants", "banian", "banians"
]

def main():
    resolver = DimensionValueResolver(settings=SETTINGS)
    
    # Set cache directly to bypass database load
    resolver.cache.put("offline-conn", INDEXED_VALUES)

    exact_matcher = ExactMatcher()
    normalized_matcher = NormalizedMatcher()
    sp_matcher = SingularPluralMatcher()
    fuzzy_matcher = FuzzyMatcher()

    sp_pipeline = MatchingPipeline([sp_matcher])
    full_pipeline = MatchingPipeline([exact_matcher, normalized_matcher, sp_matcher, fuzzy_matcher])

    print("="*80)
    print("OFFLINE POST-FIX SHORT TOKEN SAFETY AUDIT")
    print("="*80)

    for query in QUERIES:
        print(f"\nQUERY: \"{query}\"")
        
        sanitized = QuestionSanitizer.sanitize(query)
        normalized_q = resolver._normalize_text(sanitized)
        q_tokens = [t for t in normalized_q.split() if t not in STOPWORDS]
        q_singulars = [SingularPluralMatcher._to_singular(t) for t in q_tokens]

        question_context = QuestionContext(
            raw_question=sanitized,
            normalized_question=normalized_q,
            q_tokens=q_tokens,
            q_singulars=q_singulars
        )

        matching_context = MatchingContext(
            question_context=question_context,
            connection_id="offline-conn",
            indexed_values=INDEXED_VALUES,
            settings=SETTINGS
        )

        # SP Matcher candidates count
        sp_matches, _ = sp_pipeline.execute(matching_context)
        print(f"  Singular/Plural candidates BEFORE containment: {len(sp_matches)}")
        for m in sp_matches[:5]:
            print(f"    - {m.value} ({m.match_type.value})")
        if len(sp_matches) > 5:
            print(f"    - ... and {len(sp_matches)-5} more")

        # Full pipeline resolve count
        final_results = resolver.resolve_matches("offline-conn", query)
        print(f"  Final survivors count: {len(final_results)}")
        for idx, r in enumerate(final_results[:5]):
            print(f"    {idx+1}. {r['value']} ({r['match_type']})")
        if len(final_results) > 5:
            print(f"    ... and {len(final_results)-5} more")

if __name__ == "__main__":
    main()
