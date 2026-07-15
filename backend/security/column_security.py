# from security.security_rules import COLUMN_ACCESS


# def apply_column_security(rows, role):

#     allowed_columns = COLUMN_ACCESS.get(role)

#     if allowed_columns is None:
#         return rows

#     filtered_rows = []

#     for row in rows:

#         filtered_rows.append(
#             {
#                 key: value
#                 for key, value in row.items()
#                 if key in allowed_columns
#             }
#         )

#     return filtered_rows