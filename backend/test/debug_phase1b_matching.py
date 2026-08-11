import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from semantic.matching import (
    MatchingPipeline,
    MatchingContext,
    QuestionContext,
    ExactMatcher,
    NormalizedMatcher,
    SingularPluralMatcher,
    FuzzyMatcher,
    STOPWORDS,
    QuestionSanitizer,
)
from semantic.matching.models import MatchType
from semantic.dimension_value_resolver import DimensionValueResolver


def print_matches(question, indexed_values):
    print()
    print("=" * 80)
    print(f"QUESTION: {question}")
    print("=" * 80)

    sanitized = QuestionSanitizer.sanitize(question)
    normalized = DimensionValueResolver._normalize_text(sanitized)

    q_tokens = [
        token
        for token in normalized.split()
        if token not in STOPWORDS
    ]

    q_singulars = [
        SingularPluralMatcher._to_singular(token)
        for token in q_tokens
    ]

    question_context = QuestionContext(
        raw_question=sanitized,
        normalized_question=normalized,
        q_tokens=q_tokens,
        q_singulars=q_singulars,
    )

    context = MatchingContext(
        question_context=question_context,
        connection_id="debug",
        indexed_values=indexed_values,
        settings={},
    )

    matchers = [
        ExactMatcher(),
        NormalizedMatcher(),
        SingularPluralMatcher(),
        FuzzyMatcher(),
    ]

    pipeline = MatchingPipeline(matchers)

    matches, stats = pipeline.execute(context)

    print()
    print("PIPELINE STATISTICS")
    print("-" * 80)
    print(f"Exact candidates       : {stats.exact_match_count}")
    print(f"Normalized candidates  : {stats.normalized_match_count}")
    print(f"Plural candidates      : {stats.plural_match_count}")
    print(f"Fuzzy candidates       : {stats.fuzzy_match_count}")
    print(f"Total candidates       : {stats.total_match_count}")
    print()

    print("RAW MATCHES")
    print("-" * 80)

    for index, match in enumerate(matches, start=1):
        print(f"[{index}]")
        print(f"  value                 : {match.value}")
        print(f"  normalized_value      : {match.normalized_value}")
        print(f"  match_type            : {match.match_type.value}")
        print(f"  confidence            : {match.confidence}")
        print(f"  matched_question      : {match.matched_question_tokens}")
        print(f"  matched_value         : {match.matched_value_tokens}")
        print(f"  reason                : {match.reason}")
        print(f"  dimension_id          : {match.dimension_id}")
        print(f"  business_name         : {match.business_name}")
        print(f"  table_name            : {match.table_name}")
        print(f"  column_name           : {match.column_name}")
        print()


if __name__ == "__main__":
    print("Phase 1B diagnostic.")
    print()
    print(
        "This diagnostic requires the real indexed values. "
        "Run it only after wiring indexed_values from the existing resolver."
    )