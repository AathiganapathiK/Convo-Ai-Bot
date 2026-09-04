"""
Gate 3 - the empty-ambiguity response bug.

"Show sales for Mumbai" ties multiple candidates, all unreachable from
Sales with no explicit qualifier, so DimensionValueResolver's
all-unreachable/unqualified collapse correctly empties value_matches. But
PromptBuilder.build_sql_prompt()'s STRONG_AMBIGUITY response branch
(ai/prompt_builder.py) raised AmbiguityException unconditionally, building
an empty `options` list into a "Please choose one" message with nothing to
choose - reproduced live as:

    I found multiple possible matches for "Show sales for Mumbai".
    Please choose one:


Fixed by gating that raise on `if options:` - an empty collapse now falls
through, unmodified, to the existing unresolved-value/escalation handling
(the SemanticRetrievalException fallback already below it). A genuine,
non-empty tie (e.g. "coimbator city") is unaffected.

DB-gated, following this session's established pattern for live-resolver
tests.

    python -m unittest backend.test.test_empty_strong_ambiguity_response
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

mock_conn = None


def _db_reachable():
    try:
        import core.config  # noqa
        from database import engine
        with engine.connect():
            return True
    except Exception:
        return False


@unittest.skipUnless(_db_reachable(), "database not reachable in this environment")
class TestEmptyStrongAmbiguityResponse(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "semantic_benchmark"))
        import run_retrieval_benchmark as runner
        cls.conn_id = runner.resolve_logical_connection()

    def _ask(self, question):
        from ai.prompt_builder import PromptBuilder
        from unittest.mock import MagicMock
        row = {
            "connection_id": self.conn_id,
            "connection_name": "Test DB",
            "database_type": "mssql",
        }
        with patch("services.connection_service.ConnectionService") as mock_conn_service:
            mock_conn_service.get_active_connection.return_value = row
            mock_conn_service.get_connection.return_value = row
            return PromptBuilder().build_sql_prompt(question, connection_id=self.conn_id)

    # 1 - the traced live case: an all-unreachable, unqualified tie that
    # collapsed to zero candidates must NOT raise "please choose one" with
    # an empty option list.
    def test_bare_mumbai_does_not_raise_empty_clarification(self):
        from core.exceptions import AmbiguityException

        try:
            self._ask("Show sales for Mumbai")
        except AmbiguityException as exc:
            options = (exc.details or {}).get("options") or []
            self.assertTrue(
                options,
                "AmbiguityException raised with an empty options list - "
                "this is exactly the bug: %r" % exc.message,
            )
        except Exception:
            # Any other outcome (e.g. SemanticRetrievalException from the
            # fallback this now correctly falls through to) is fine - the
            # only forbidden outcome is an empty-options AmbiguityException.
            pass

    # 2 - a genuine, non-empty STRONG_AMBIGUITY tie must still raise the
    # clarification exactly as before.
    def test_genuine_tie_still_raises_clarification_with_options(self):
        from core.exceptions import AmbiguityException

        with self.assertRaises(AmbiguityException) as ctx:
            self._ask("Show sales for coimbator city")
        options = (ctx.exception.details or {}).get("options") or []
        self.assertTrue(options)
        values = {opt["value"] for opt in options}
        self.assertEqual(values, {"COIMBATORE", "ELECTRONIC CITY"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
