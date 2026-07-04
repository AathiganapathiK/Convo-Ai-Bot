from collections import defaultdict

MAX_HISTORY = 5

conversation_store = defaultdict(
    lambda: defaultdict(list)
)


def get_history(
    employee_id,
    conversation_id="default"
):

    employee_id = str(employee_id)

    return conversation_store[
        employee_id
    ][
        conversation_id
    ]


def add_exchange(
    employee_id,
    question,
    sql_query,
    conversation_id="default"
):
    employee_id = str(employee_id)
    conversation_store[
                            employee_id
                        ][
                            conversation_id
                        ].append(
        {
            "question": question,
            "sql_query": sql_query
        }
    )

    if (
        len(
            conversation_store[
                employee_id
            ][
                conversation_id
            ]
        )
        > MAX_HISTORY
    ):
        conversation_store[
            employee_id
        ][
            conversation_id
        ].pop(0)


"""
Why Store SQL Instead of Summary?

The SQL contains the exact analytical intent.

The summary is only a narrative.

Therefore SQL is far more useful for follow-up questions.
"""