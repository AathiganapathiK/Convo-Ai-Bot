import os 
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time

from ai.sql_validator import validate_sql_query

queries = [
    "SELECT Sales FROM Sales",
    "SELECT TOP 10 Sales FROM Sales",
    "SELECT S.Sales, P.Product FROM Sales S JOIN Products P ON S.ProductKey=P.ProductKey",
    "SELECT SUM(Sales) FROM Sales GROUP BY ProductKey",
    "SELECT Sales FROM Sales WHERE Sales > 1000",
] * 100   # 500 queries

start = time.perf_counter()

passed = 0

for sql in queries:
    ok, _ = validate_sql_query(sql)
    if ok:
        passed += 1

end = time.perf_counter()

total = end - start

print("=" * 60)
print("Performance Report")
print("=" * 60)

print(f"Queries        : {len(queries)}")
print(f"Passed         : {passed}")
print(f"Total Time     : {total:.4f} sec")
print(f"Average Time   : {(total/len(queries))*1000:.2f} ms/query")