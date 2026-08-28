"""
Tests for Gate 2 Step 8, the configuration suggestion service.

No database and no model. Every test feeds hand-made column profiles to the
pure logic, so the whole file runs offline in under a second.

WHAT THIS FILE IS FOR
    Five defects were found in config_suggester by running it against real data
    and reading the output by hand. Two of them hid themselves - the service
    reported plausible-looking proposals while silently discarding every model
    answer. Manual inspection found them once; these tests stop them returning.

    The privacy tests matter most. They are the ones that must fail loudly if
    anybody ever widens the gate, because the cost of getting that wrong is
    customer and employee names leaving the network.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from semantic.config_suggester import (  # noqa: E402
    ConfigSuggester,
    CLASSIFICATIONS,
    DIMENSION_ROLES,
    MEASURE_KINDS,
    PERIOD_SCOPES,
)


class ExplodingConnection:
    """
    Records whether it was used, and refuses to serve data if it is.

    Proves that a withheld column's values are never READ, not merely that they
    are absent from the output. Withholding after reading would still keep the
    values out of the payload, but the guarantee this service makes is stronger:
    it does not touch them.

    Raising alone is not enough to prove this. _gate_samples wraps its query in
    a broad except, so an exception raised here is swallowed and the column is
    marked withheld regardless - which means a test relying only on the withheld
    flag passes even with the privacy gate deleted. Mutation testing caught
    exactly that false pass. Callers must therefore assert `used` is False.
    """

    def __init__(self):
        self.used = False

    def execute(self, *args, **kwargs):
        self.used = True
        raise AssertionError("Values read for a column that must never be sampled.")


class FakeConnection:
    """Returns fixed rows, for the cases where sampling is legitimate."""

    def __init__(self, values):
        self._values = values
        self.queried = False

    def execute(self, *args, **kwargs):
        self.queried = True
        return self

    def fetchall(self):
        return [(v,) for v in self._values]


def profile(column_name, data_type="nvarchar", distinct=5, rows=1000):
    return {
        "column_name": column_name,
        "data_type": data_type,
        "row_count_profiled": rows,
        "distinct_count": distinct,
        "null_fraction": 0.0,
        "samples": [],
        "samples_withheld": False,
        "samples_withheld_reason": None,
    }


# ---------------------------------------------------------------------------
# Privacy. The most important tests in the file.
# ---------------------------------------------------------------------------


class TestPrivacyGate(unittest.TestCase):

    def test_personal_name_column_is_never_read_however_few_values(self):
        """
        The defect that made this gate necessary.

        RMNAME holds eight distinct values, comfortably under the cardinality
        limit, and every one of them is a real person's name. Low cardinality is
        not evidence that data is impersonal.
        """
        p = profile("RMNAME", distinct=8)
        conn = ExplodingConnection()
        ConfigSuggester._gate_samples(conn, "T", p)

        self.assertFalse(conn.used, "The database was queried for a person's name.")
        self.assertTrue(p["samples_withheld"])
        self.assertEqual(p["samples"], [])
        self.assertIn("person", p["samples_withheld_reason"].lower())

    def test_every_personal_name_pattern_is_withheld(self):
        for pattern in ConfigSuggester.PERSONAL_NAME_PATTERNS:
            with self.subTest(pattern=pattern):
                p = profile(f"col_{pattern}_x", distinct=3)
                conn = ExplodingConnection()
                ConfigSuggester._gate_samples(conn, "T", p)
                self.assertFalse(
                    conn.used,
                    f"A column named after '{pattern}' had its values read.",
                )
                self.assertTrue(p["samples_withheld"])

    def test_real_name_columns_from_this_database(self):
        for column in ("CardName", "GCardName", "RMNAME", "cardname", "Cardname"):
            with self.subTest(column=column):
                p = profile(column, distinct=7)
                conn = ExplodingConnection()
                ConfigSuggester._gate_samples(conn, "T", p)
                self.assertFalse(conn.used, f"{column} had its values read.")
                self.assertTrue(p["samples_withheld"])

    def test_high_cardinality_column_is_never_read(self):
        p = profile("CardCode", distinct=27781, rows=2238958)
        conn = ExplodingConnection()
        ConfigSuggester._gate_samples(conn, "T", p)

        self.assertFalse(conn.used, "A high-cardinality column had its values read.")
        self.assertTrue(p["samples_withheld"])
        self.assertEqual(p["samples"], [])
        self.assertIn("27,781", p["samples_withheld_reason"])

    def test_uncountable_column_is_never_read(self):
        """A column whose cardinality could not be established is not sampled."""
        p = profile("Notes", distinct=None)
        ConfigSuggester._gate_samples(ExplodingConnection(), "T", p)
        self.assertTrue(p["samples_withheld"])

    def test_boundary_of_the_cardinality_limit(self):
        limit = ConfigSuggester.SAMPLE_CARDINALITY_LIMIT

        at_limit = profile("Category", distinct=limit)
        ConfigSuggester._gate_samples(FakeConnection(["A", "B"]), "T", at_limit)
        self.assertFalse(at_limit["samples_withheld"], "At the limit should be sampled.")

        over_limit = profile("Category", distinct=limit + 1)
        conn = ExplodingConnection()
        ConfigSuggester._gate_samples(conn, "T", over_limit)
        self.assertFalse(conn.used, "A column over the limit had its values read.")
        self.assertTrue(over_limit["samples_withheld"], "Over the limit must not be.")

    def test_ordinary_low_cardinality_column_is_sampled(self):
        p = profile("InvMonth", distinct=12)
        conn = FakeConnection(["A April", "B May", "C June"])
        ConfigSuggester._gate_samples(conn, "T", p)

        self.assertFalse(p["samples_withheld"])
        self.assertEqual(p["samples"], ["A April", "B May", "C June"])
        self.assertTrue(conn.queried)

    def test_no_withheld_profile_ever_carries_values(self):
        """
        The leak test. Whatever the reason for withholding, the values must be
        absent and the reason must be present - the review screen relies on the
        reason to explain an empty evidence box rather than looking broken.
        """
        cases = [
            profile("CardName", distinct=4),
            profile("CustomerCode", distinct=2),
            profile("Anything", distinct=999999),
            profile("Unknown", distinct=None),
        ]
        for p in cases:
            with self.subTest(column=p["column_name"]):
                conn = ExplodingConnection()
                ConfigSuggester._gate_samples(conn, "T", p)
                self.assertFalse(conn.used)
                self.assertTrue(p["samples_withheld"])
                self.assertEqual(p["samples"], [])
                self.assertIsNotNone(p["samples_withheld_reason"])
                self.assertNotEqual(p["samples_withheld_reason"].strip(), "")


# ---------------------------------------------------------------------------
# The defect that made the service look broken while the model worked perfectly
# ---------------------------------------------------------------------------


class TestModelOutputIsActuallyUsed(unittest.TestCase):

    def test_parse_returns_the_model_shape_not_an_unwrapped_one(self):
        """
        Regression for the double-unwrap defect.

        _parse_model_output used to unwrap "columns" itself, so _ask_model
        unwrapped an already-unwrapped dict, got nothing, and threw away every
        answer. The service reported confident-looking proposals that no model
        had made. It must return the shape the model sent.
        """
        raw = '{"columns": {"InvMonth": {"classification": "DIMENSION"}}}'
        parsed = ConfigSuggester._parse_model_output(raw)

        self.assertIn("columns", parsed)
        self.assertIn("InvMonth", parsed["columns"])

    def test_a_model_verdict_reaches_the_suggestion(self):
        verdicts = {
            "InvMonth": {
                "classification": "DIMENSION",
                "business_name": "Invoice Month",
                "dimension_role": "TIME_LABEL",
                "confidence": 0.96,
                "reasoning": "Twelve month labels.",
            }
        }
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("InvMonth", distinct=12)], verdicts,
            {"columns": {}, "tables": {}},
        )[0]

        self.assertEqual(out["proposal"]["business_name"], "Invoice Month")
        self.assertEqual(out["proposal"]["dimension_role"], "TIME_LABEL")
        self.assertEqual(out["confidence"], 0.96)
        self.assertTrue(out["suggested_by"].startswith("llm"))

    def test_no_verdict_falls_back_and_admits_it(self):
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("Whatever", distinct=5)], {},
            {"columns": {}, "tables": {}},
        )[0]

        self.assertEqual(out["suggested_by"], "profile-only")
        self.assertLessEqual(out["confidence"], 0.5)
        self.assertIn("profile only", out["reasoning"].lower())

    def test_identifier_is_recognised_without_a_model(self):
        p = profile("Sno", data_type="int", distinct=49873, rows=50000)
        verdict = ConfigSuggester._fallback_verdict(p)

        self.assertEqual(verdict["classification"], "EXCLUDED")
        self.assertEqual(verdict["dimension_role"], "IDENTIFIER")


# ---------------------------------------------------------------------------
# A model may return anything. Nothing outside the vocabulary may be stored.
# ---------------------------------------------------------------------------


class TestVocabularyIsEnforced(unittest.TestCase):

    def test_unknown_classification_falls_back(self):
        verdicts = {"X": {"classification": "PROBABLY_A_NUMBER", "confidence": 0.9}}
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("X")], verdicts, {"columns": {}, "tables": {}},
        )[0]
        self.assertIn(out["proposal"]["classification"], CLASSIFICATIONS)

    def test_unknown_role_becomes_none_rather_than_free_text(self):
        verdicts = {"X": {"classification": "DIMENSION", "dimension_role": "Time Label"}}
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("X")], verdicts, {"columns": {}, "tables": {}},
        )[0]
        role = out["proposal"]["dimension_role"]
        self.assertTrue(role is None or role in DIMENSION_ROLES)

    def test_lowercase_vocabulary_is_accepted(self):
        verdicts = {"X": {"classification": "dimension", "dimension_role": "grouping"}}
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("X")], verdicts, {"columns": {}, "tables": {}},
        )[0]
        self.assertEqual(out["proposal"]["classification"], "DIMENSION")
        self.assertEqual(out["proposal"]["dimension_role"], "GROUPING")

    def test_confidence_is_clamped(self):
        self.assertEqual(ConfigSuggester._clamp_confidence(5.0), 1.0)
        self.assertEqual(ConfigSuggester._clamp_confidence(-3), 0.0)
        self.assertIsNone(ConfigSuggester._clamp_confidence("very sure"))
        self.assertIsNone(ConfigSuggester._clamp_confidence(None))
        self.assertEqual(ConfigSuggester._clamp_confidence(0.5), 0.5)

    def test_fiscal_month_is_clamped(self):
        self.assertEqual(ConfigSuggester._clamp_month(4), 4)
        self.assertIsNone(ConfigSuggester._clamp_month(13))
        self.assertIsNone(ConfigSuggester._clamp_month(0))
        self.assertIsNone(ConfigSuggester._clamp_month("April"))

    def test_aggregation_only_survives_on_a_measure(self):
        verdicts = {"X": {"classification": "DIMENSION", "aggregation_type": "SUM"}}
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("X")], verdicts, {"columns": {}, "tables": {}},
        )[0]
        self.assertIsNone(
            out["proposal"]["aggregation_type"],
            "A dimension must not carry an aggregation.",
        )


# ---------------------------------------------------------------------------
# Model replies are not always well-formed
# ---------------------------------------------------------------------------


class TestParsingIsRobust(unittest.TestCase):

    def test_code_fenced_json(self):
        raw = '```json\n{"columns": {"A": {"classification": "MEASURE"}}}\n```'
        self.assertIn("A", ConfigSuggester._parse_model_output(raw).get("columns", {}))

    def test_json_wrapped_in_prose(self):
        raw = 'Sure! Here is the result:\n{"columns": {"A": {}}}\nHope that helps.'
        self.assertIn("columns", ConfigSuggester._parse_model_output(raw))

    def test_two_concatenated_objects(self):
        """
        Observed in practice. Slicing from the first brace to the last spans
        both objects and fails; only the first should be read.
        """
        raw = '{"columns": {"A": {}}}{"columns": {"B": {}}}'
        parsed = ConfigSuggester._parse_model_output(raw)
        self.assertIn("A", parsed.get("columns", {}))

    def test_truncated_json_degrades_quietly(self):
        raw = '{"columns": {"A": {"classification": "DIMENS'
        self.assertEqual(ConfigSuggester._parse_model_output(raw), {})

    def test_no_json_at_all(self):
        self.assertEqual(ConfigSuggester._parse_model_output("I cannot help."), {})
        self.assertEqual(ConfigSuggester._parse_model_output(""), {})

    def test_json_that_is_not_an_object(self):
        self.assertEqual(ConfigSuggester._parse_model_output("[1, 2, 3]"), {})


class TestRateLimitDetection(unittest.TestCase):

    def test_provider_wait_is_honoured(self):
        exc = Exception("Error code: 429 - rate_limit_exceeded. Please try again in 9.945s.")
        wait = ConfigSuggester._rate_limit_wait(exc)
        self.assertIsNotNone(wait)
        self.assertGreater(wait, 9.9)

    def test_rate_limit_without_a_stated_wait(self):
        self.assertIsNotNone(
            ConfigSuggester._rate_limit_wait(Exception("429 Too Many Requests"))
        )

    def test_other_errors_are_not_retried(self):
        self.assertIsNone(ConfigSuggester._rate_limit_wait(Exception("Connection refused")))


# ---------------------------------------------------------------------------
# The output shape is a contract with Step 9 and Step 10
# ---------------------------------------------------------------------------


class TestOutputContract(unittest.TestCase):

    COLUMN_KEYS = {
        "suggestion_id", "table_name", "column_name", "target", "proposal",
        "current", "evidence", "confidence", "reasoning", "is_confirmed",
        "suggested_at", "suggested_by",
    }
    EVIDENCE_KEYS = {
        "data_type", "distinct_count", "null_fraction", "samples",
        "samples_withheld", "samples_withheld_reason", "row_count_profiled",
    }

    def test_column_suggestion_carries_every_agreed_key(self):
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("X")], {}, {"columns": {}, "tables": {}},
        )[0]
        self.assertEqual(set(out.keys()), self.COLUMN_KEYS)
        self.assertEqual(set(out["evidence"].keys()), self.EVIDENCE_KEYS)
        self.assertFalse(out["is_confirmed"], "Nothing may be proposed as confirmed.")

    def test_a_proposal_reads_as_a_change_not_a_fact(self):
        """
        The current block is why the screen can say "this is a metric today and
        the proposal moves it", instead of asserting an answer with no context.
        """
        current = {
            "columns": {
                ("T", "DocMonth"): {
                    "exists": True,
                    "config_table": "semantic_metrics",
                    "classification": "MEASURE",
                    "business_name": "Doc Month",
                    "is_excluded": False,
                }
            },
            "tables": {},
        }
        verdicts = {"DocMonth": {"classification": "DIMENSION", "dimension_role": "TIME_LABEL"}}
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("DocMonth", data_type="int", distinct=12)], verdicts, current,
        )[0]

        self.assertEqual(out["current"]["classification"], "MEASURE")
        self.assertEqual(out["proposal"]["classification"], "DIMENSION")
        self.assertEqual(out["target"]["config_table"], "semantic_dimensions")

    def test_unknown_column_reports_no_current_configuration(self):
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("Brand new")], {}, {"columns": {}, "tables": {}},
        )[0]
        self.assertFalse(out["current"]["exists"])

    def test_excluding_a_column_keeps_it_where_it_already_lives(self):
        """
        EXCLUDED is a decision about visibility, not about which table the row
        belongs in. Moving it as well would create an orphan.
        """
        current = {
            "columns": {
                ("T", "Sno"): {
                    "exists": True,
                    "config_table": "semantic_metrics",
                    "classification": "MEASURE",
                    "business_name": "Sno",
                    "is_excluded": False,
                }
            },
            "tables": {},
        }
        out = ConfigSuggester._build_column_suggestions(
            "T", [profile("Sno", data_type="int")],
            {"Sno": {"classification": "EXCLUDED"}}, current,
        )[0]

        self.assertTrue(out["proposal"]["is_excluded"])
        self.assertEqual(out["target"]["config_table"], "semantic_metrics")

    def test_evidence_travels_with_the_proposal(self):
        p = profile("CardName", distinct=27781, rows=2238958)
        ConfigSuggester._gate_samples(ExplodingConnection(), "T", p)
        # (this one asserts on the payload, not on access - see the privacy tests)
        out = ConfigSuggester._build_column_suggestions(
            "T", [p], {}, {"columns": {}, "tables": {}},
        )[0]

        self.assertTrue(out["evidence"]["samples_withheld"])
        self.assertIsNotNone(out["evidence"]["samples_withheld_reason"])
        self.assertEqual(out["evidence"]["samples"], [])
        self.assertEqual(out["evidence"]["distinct_count"], 27781)


class TestTableSuggestion(unittest.TestCase):

    def test_snapshot_mappings_are_validated(self):
        verdicts = {
            "__table__": {
                "temporal_strategy": "SNAPSHOT",
                "snapshot_mappings": [
                    {"period_offset": 0, "measure_kind": "VALUE",
                     "period_scope": "TO_DATE", "column_name": "CY"},
                    {"period_offset": 1, "measure_kind": "QUANTITY",
                     "period_scope": "FULL", "column_name": "PYQ"},
                    # Rejected: no column
                    {"period_offset": 2, "measure_kind": "VALUE",
                     "period_scope": "FULL", "column_name": None},
                    # Rejected: offset is not a number
                    {"period_offset": "last", "measure_kind": "VALUE",
                     "period_scope": "FULL", "column_name": "PPY"},
                    # Vocabulary outside the agreed set is corrected, not stored
                    {"period_offset": 3, "measure_kind": "MONEY",
                     "period_scope": "PARTIAL", "column_name": "PPPY"},
                ],
            }
        }
        out = ConfigSuggester._build_table_suggestion(
            "T", [profile("CY"), profile("PYQ")], verdicts, {"columns": {}, "tables": {}},
        )
        mappings = out["snapshot_mappings"]

        self.assertEqual(len(mappings), 3, "Two malformed entries should be dropped.")
        for m in mappings:
            self.assertIn(m["measure_kind"], MEASURE_KINDS)
            self.assertIn(m["period_scope"], PERIOD_SCOPES)
            self.assertGreaterEqual(m["period_offset"], 0)

    def test_the_full_versus_to_date_distinction_survives(self):
        """
        PY and PYTD differ only by period_scope, and that difference is the gap
        between reporting growth and reporting a collapse. Nothing may collapse
        them into one entry.
        """
        verdicts = {
            "__table__": {
                "temporal_strategy": "SNAPSHOT",
                "snapshot_mappings": [
                    {"period_offset": 1, "measure_kind": "VALUE",
                     "period_scope": "FULL", "column_name": "PY"},
                    {"period_offset": 1, "measure_kind": "VALUE",
                     "period_scope": "TO_DATE", "column_name": "PYTD"},
                ],
            }
        }
        out = ConfigSuggester._build_table_suggestion(
            "T", [profile("PY"), profile("PYTD")], verdicts, {"columns": {}, "tables": {}},
        )
        scopes = {m["column_name"]: m["period_scope"] for m in out["snapshot_mappings"]}

        self.assertEqual(scopes["PY"], "FULL")
        self.assertEqual(scopes["PYTD"], "TO_DATE")

    def test_table_suggestion_is_never_pre_confirmed(self):
        out = ConfigSuggester._build_table_suggestion(
            "T", [profile("X")], {}, {"columns": {}, "tables": {}},
        )
        self.assertFalse(out["is_confirmed"])
        self.assertIsNone(out["proposal"]["temporal_strategy"])

    def test_output_is_json_serialisable(self):
        """It crosses an API boundary, so it has to survive serialisation."""
        result = {
            "table_suggestions": [
                ConfigSuggester._build_table_suggestion(
                    "T", [profile("X")], {}, {"columns": {}, "tables": {}})
            ],
            "column_suggestions": ConfigSuggester._build_column_suggestions(
                "T", [profile("X")], {}, {"columns": {}, "tables": {}}),
        }
        self.assertIsInstance(json.dumps(result), str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
