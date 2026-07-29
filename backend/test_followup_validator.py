from ai.insights.followup_validator import FollowupValidator


def main():

    # Replace with a real enabled datasource connection ID
    connection_id = '6692FD9B-A032-43CA-A39E-F13AE1CAA208'

    questions = [
        "Show total sales by year",
        "Compare sales by region",
        "Analyze customer acquisition cost",
        "Show sales by marketing channel",
        "List top selling products"
    ]

    print("=" * 60)
    print("FOLLOWUP VALIDATOR TEST")
    print("=" * 60)

    original_question = "What is the total sales?"

    valid_questions = FollowupValidator.validate(
        questions=questions,
        original_question=original_question,
        connection_id=connection_id
    )

    print("\n")
    print("=" * 60)
    print("VALID QUESTIONS")
    print("=" * 60)

    for i, question in enumerate(valid_questions, start=1):
        print(f"{i}. {question}")


if __name__ == "__main__":
    main()