import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.matching.candidate_phrase_extractor import CandidatePhraseExtractor
from semantic.matching.fuzzy_matcher import FuzzyMatcher
from semantic.matching.models import MatchingContext, QuestionContext, CachedDimensionValue
from semantic.matching.confidence import MatchSettings
from semantic.dimension_value_resolver import DimensionValueResolver
from rapidfuzz import fuzz, process

def get_extractor_phrases(q):
    extractor = CandidatePhraseExtractor()
    return extractor.extract(q)

def run_audit():
    indexed_words = [
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
    
    indexed_values = []
    for idx, val in enumerate(indexed_words):
        norm_val = DimensionValueResolver._normalize_text(val)
        val_tokens = norm_val.split()
        val_singulars = [DimensionValueResolver._is_contiguous_sublist # mock-like, but let's use the real singular helper:
                         for t in val_tokens]
        # Let's import SingularPluralMatcher to get singulars properly
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher
        val_singulars = [SingularPluralMatcher._to_singular(t) for t in val_tokens]
        
        indexed_values.append(CachedDimensionValue(
            semantic_dimension_id=idx + 1,
            business_name="Category",
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

    # Q1: Candidate Generation
    print("--- QUESTION 1: CANDIDATE PHRASE GENERATION ---")
    q_list = [
        "show sales for pant",
        "show sales for cotton pant",
        "show sales for formal shirt",
        "show sales for cotton pants",
        "show sales in tamil nadu",
        "show monthly sales by region"
    ]
    for q in q_list:
        phrases = get_extractor_phrases(q)
        print(f"Question: {q!r}")
        print(f"Generated: {phrases}")
        print()

    # Q2: Comparison Volume
    print("--- QUESTION 2: FUZZY COMPARISON VOLUME ---")
    for q in q_list:
        phrases = get_extractor_phrases(q)
        num_phrases = len(phrases)
        num_indexed = len(indexed_values)
        total_comps = num_phrases * num_indexed
        print(f"Question: {q!r} -> Phrases: {num_phrases}, Indexed: {num_indexed}, Comparisons: {total_comps}")
    print()

    # Q3 & Q4 & Q5 & Q6 & Q7: Candidate Scoring & Business Cases
    print("--- QUESTIONS 3-7: DETAILED CANDIDATE SCORING ---")
    test_questions = [
        "pant",
        "cotton pant",
        "formal pant",
        "shirt",
        "formal shirt",
        "cotton shirt",
        "tshirt",
        "banian",
        "child wear",
        "mens wear",
        "women wear",
        "person choice",
        "laptop",
        "banana",
        "hospital",
        "customer",
        "xyzabc",
        "cottn pant",
        "forml shirt",
        "childern wear",
        "womens wear",
        "persn choice",
        "wear",
        "men",
        "women",
        "cotton"
    ]
    
    fuzzy_matcher = FuzzyMatcher()
    cutoff = MatchSettings.FUZZY_SCORE_CUTOFF
    
    for q in test_questions:
        print(f"\n==================================================")
        print(f"Question: {q!r}")
        phrases = get_extractor_phrases(q)
        print(f"Phrases: {phrases}")
        
        # We want to report ALL candidate comparison scores for this question
        # matching what process.extract or the scorer does.
        # Let's run the exact rapidfuzz process.extract loop to show all candidates
        candidate_strings = [val.normalized_value for val in indexed_values]
        
        scored_candidates = []
        for phrase in phrases:
            for val in indexed_values:
                # WRatio score
                score = fuzz.WRatio(phrase, val.normalized_value)
                length_diff = abs(len(val.normalized_value) - len(phrase))
                passed = score >= cutoff
                scored_candidates.append({
                    "phrase": phrase,
                    "val": val.value,
                    "score": score,
                    "length_diff": length_diff,
                    "passed": passed
                })
        
        # Sort by score descending, then length diff ascending
        scored_candidates.sort(key=lambda x: (-x["score"], x["length_diff"]))
        
        print("Scored Candidates (all):")
        for sc in scored_candidates:
            print(f"  Phrase: {sc['phrase']!r} | Val: {sc['val']!r} | Score: {sc['score']:.1f} | LenDiff: {sc['length_diff']} | Passed: {sc['passed']}")

        # Trace match() output
        norm_q = DimensionValueResolver._normalize_text(q)
        q_tokens = norm_q.split()
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher
        q_singulars = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
        q_context = QuestionContext(
            raw_question=q,
            normalized_question=norm_q,
            q_tokens=q_tokens,
            q_singulars=q_singulars
        )
        ctx = MatchingContext(
            question_context=q_context,
            connection_id="mock",
            indexed_values=indexed_values,
            settings=None
        )
        matched_res = fuzzy_matcher.match(ctx)
        print("FuzzyMatcher.match() output:")
        if matched_res:
            for mr in matched_res:
                print(f"  Winner Value: {mr.value!r} | Score: {mr.confidence * 100:.1f} | MatchType: {mr.match_type.name} | Reason: {mr.reason}")
        else:
            print("  None")

if __name__ == "__main__":
    run_audit()
