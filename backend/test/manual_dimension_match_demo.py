import os
import sys

sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

from semantic.dimension_value_resolver import DimensionValueResolver


def run(question):
    print("=" * 80)
    print(f"Question : {question}")

    results = DimensionValueResolver.resolve(
        connection_id="6692FD9B-A032-43CA-A39E-F13AE1CAA208",
        question=question
    )

    if not results:
        print("❌ No Match")
        return

    for result in results:
        print(f"Matched Value : {result['value']}")
        print(f"Business Name : {result['business_name']}")
        print(f"Column        : {result['column_name']}")
        print(f"Match Type    : {result['match_type']}")
        print(f"Confidence    : {result['confidence']}")


if __name__ == "__main__":

    test_queries = [

        # Exact
        "Banians",

        # Singular
        "Banian",

        # Plural
        "Shirt",

        # Typo
        "Banain",

        # Typo
        "Baniaan",

        # Typo
        "Bniyan",

        # Typo
        "Cottn Shirt",

        # Space
        "Ramraj",

        # Hyphen
        "Ram Raj",

        # Normalization
        "T Shirt",

        # Apostrophe
        "Mens Wear",

        # Stopwords
        "Show me Banian sales",

        # Stopwords
        "Give cotton pant sales",

        # Negative
        "Laptop",

        # Negative
        "Computer",

        # Negative
        "Phone"

    ]

    for query in test_queries:
        run(query)