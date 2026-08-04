from sqlglot import exp

"""
AST Security Constants.
"""

ALLOWED_ROOT_NODE_TYPES = (
    exp.Select,
    exp.Union,
)

BLOCKED_NODE_TYPES = (
    exp.Drop,
    exp.Delete,
    exp.Insert,
    exp.Update,
    exp.Alter,
    exp.Create,
    exp.Merge,
    exp.TruncateTable,
    exp.Execute,
)

NODE_DISPLAY_NAMES = {
    exp.Drop: "DROP",
    exp.Delete: "DELETE",
    exp.Insert: "INSERT",
    exp.Update: "UPDATE",
    exp.Alter: "ALTER",
    exp.Create: "CREATE",
    exp.Merge: "MERGE",
    exp.TruncateTable: "TRUNCATE",
    exp.Execute: "EXECUTE",
}