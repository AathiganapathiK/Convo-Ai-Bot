from ai.sql_validator import validate_sql_query
from ai.sql_validator import validate_schema

sql = """
SELECT *
FROM InvalidTable
"""

print(validate_sql_query(sql))