"""
AST Security Validator.
"""

from dataclasses import dataclass
from typing import Dict, List, Union
from sqlglot import exp

from .constants import ALLOWED_ROOT_NODE_TYPES, BLOCKED_NODE_TYPES, NODE_DISPLAY_NAMES


@dataclass
class SecurityValidationResult:
    """
    Model representing the outcome of a security validation check.
    """
    passed: bool
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Union[bool, List[str]]]:
        """
        Convert validation results to standard dictionary format.
        """
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class SQLASTSecurityValidator:
    """
    Validates the security of a parsed SQL AST.
    Checks for multiple statements and dangerous AST nodes.
    """

    def validate_ast(self, ast: exp.Expression) -> SecurityValidationResult:
        """
        Validate an AST expression against security rules.

        Args:
            ast: The parsed SQL AST Expression from sqlglot.

        Returns:
            SecurityValidationResult containing passed status, errors, and warnings.
        """
        if ast is None:
            return SecurityValidationResult(
                passed=False,
                errors=["Empty AST or invalid SQL structure."],
                warnings=[]
            )

        errors: List[str] = []
        warnings: List[str] = []

        # 1. Get root statements and check for multiple statements
        root_statements = self._get_root_statements(ast, errors)

        # 2. Validate root-level statement types
        errors.extend(self._validate_root_nodes(root_statements))

        # 3. Walk entire AST to find blocked/dangerous nodes anywhere
        errors.extend(self._validate_blocked_nodes(root_statements))

        # 4. Deduplicate errors while preserving order
        unique_errors = self._deduplicate_errors(errors)

        # 5. Build and return result object
        return self._build_result(unique_errors, warnings)

    def _get_root_statements(self, ast: exp.Expression, errors: List[str]) -> List[exp.Expression]:
        """
        Extract root statement(s) from the AST, checking for multiple statement violations.
        """
        root_statements: List[exp.Expression] = []

        if isinstance(ast, exp.Block):
            exprs = ast.expressions
            if len(exprs) > 1:
                errors.append("Multiple SQL statements detected.")
            root_statements.extend(exprs)
        else:
            root_statements.append(ast)

        return root_statements

    def _validate_root_nodes(self, root_statements: List[exp.Expression]) -> List[str]:
        """
        Verify that root-level statement types are allowed (e.g. SELECT or UNION).
        """
        errors = []
        for stmt in root_statements:
            if not isinstance(stmt, ALLOWED_ROOT_NODE_TYPES):
                stmt_class = type(stmt)
                if stmt_class in NODE_DISPLAY_NAMES:
                    display_name = NODE_DISPLAY_NAMES[stmt_class]
                    errors.append(f"{display_name} statements are not allowed.")
                else:
                    display_name = stmt_class.__name__.upper()
                    errors.append(f"Query type '{display_name}' is not allowed. Only SELECT and UNION are permitted.")
        return errors

    def _validate_blocked_nodes(self, root_statements: List[exp.Expression]) -> List[str]:
        """
        Walk the AST to search for blocked/dangerous nodes anywhere in the query.
        
        This recursively traverses the entire AST using `stmt.walk()`, which inspects
        all nested child elements (including subqueries, CTEs, EXISTS clauses, 
        window functions, etc.) to detect dangerous nodes anywhere in the query.
        """
        errors = []
        for stmt in root_statements:
            for node in stmt.walk():
                if isinstance(node, BLOCKED_NODE_TYPES):
                    node_class = type(node)
                    display_name = NODE_DISPLAY_NAMES.get(node_class, node_class.__name__.upper())
                    errors.append(f"{display_name} statements are not allowed.")
        return errors

    def _deduplicate_errors(self, errors: List[str]) -> List[str]:
        """
        Deduplicate error messages while preserving their original order.
        """
        unique_errors = []
        for err in errors:
            if err not in unique_errors:
                unique_errors.append(err)
        return unique_errors

    def _build_result(self, errors: List[str], warnings: List[str]) -> SecurityValidationResult:
        """
        Construct the validation result model.
        """
        return SecurityValidationResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
