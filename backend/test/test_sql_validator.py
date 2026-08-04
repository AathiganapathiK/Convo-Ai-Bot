import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.sql_validator import validate_sql_query

queries = [

    "SELECT Sales FROM Sales",

    "SELECT InvalidColumn FROM Sales",

    "DROP TABLE Sales",

    "SELECT ProductKey FROM Sales S JOIN Products P ON S.ProductKey=P.ProductKey",

    "SELECT S.ProductKey FROM Sales S JOIN Products P ON S.ProductKey=P.ProductKey",

]

for sql in queries:
    print("="*80)
    print(sql)
    print(validate_sql_query(sql))
    print("="*80)