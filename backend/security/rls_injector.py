import re

def apply_rls(
    sql_query,
    department
):



    sql_query = sql_query.strip()

    if sql_query.endswith(";"):
        sql_query = sql_query[:-1]

    lower_sql = sql_query.lower()

    if re.search(
        r"\bdepartment\s*=",
        lower_sql
    ):
        return sql_query

    if " where " in lower_sql:

        pattern = re.compile(
            r"\b(group\s+by|order\s+by|having)\b",
            re.IGNORECASE
        )

        match = pattern.search(sql_query)

        if match:

            pos = match.start()

            return (
                sql_query[:pos]
                + f" AND department = '{department}' "
                + sql_query[pos:]
            )

        return (
            sql_query
            + f" AND department = '{department}'"
        )

    else:

        pattern = re.compile(
            r"\b(group\s+by|order\s+by|having)\b",
            re.IGNORECASE
        )

        match = pattern.search(sql_query)

        if match:

            pos = match.start()

            return (
                sql_query[:pos]
                + f" WHERE department = '{department}' "
                + sql_query[pos:]
            )

        return (
            sql_query
            + f" WHERE department = '{department}'"
        )