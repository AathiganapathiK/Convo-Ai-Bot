"""
A value universe built from committed benchmark artifacts.

WHY THIS IS NOT FABRICATED DATA

Every value here was resolved by a real run against the real database and
recorded in test/semantic_benchmark/v2/baseline_runs/*/results.json, which is
already in the repository. Nothing is invented and nothing is written back to
the semantic configuration. This module only re-reads what previous runs
observed.

WHAT IT IS NOT

It is a PARTIAL universe: it contains only values some recorded run actually
resolved. Values that exist in the database but were never resolved by any
recorded case are absent, so a case whose correct answer is one of those cannot
be judged here. The harness reports those cases as UNMEASURABLE rather than as
passes or failures, which is the honest treatment and the reason that
distinction exists at all.

The same universe feeds BOTH paths - the legacy matcher index and the
candidate_scoped provider - so the comparison between them is like for like
even though the absolute pass rate is not comparable to the real 190-case
number.
"""
import glob
import json
import os
from typing import Dict, List

from semantic.matching import CachedDimensionValue, SingularPluralMatcher
from semantic.value_provider import (
    StaticDimensionValueProvider,
    normalize_for_matching,
)

PROVENANCE_RECORDED = "recorded/benchmark-artifact"

_RUNS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "semantic_benchmark", "v2", "baseline_runs", "*", "results.json",
)


def _dimension_records():
    """
    (value, business_name, table_name, column_name) tuples from every run.

    Read from `actual.dimensions` rather than guessed: the recorded runs carry
    the resolved dimension's business name, table and column alongside the
    values, which is exactly what a provider has to supply.
    """
    seen = {}
    for path in sorted(glob.glob(_RUNS)):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue

        for record in payload.get("results", []):
            actual = record.get("actual")
            if not isinstance(actual, dict):
                continue

            dims = [d for d in (actual.get("dimensions") or []) if isinstance(d, dict)]
            values = [v for v in (actual.get("values") or []) if isinstance(v, str)]
            if not dims or not values:
                continue

            # A record may carry several dimensions and several values. Only
            # pair them when there is exactly one dimension, so no value is
            # ever attributed to a dimension it may not belong to.
            if len(dims) == 1:
                pairs = [(v, dims[0]) for v in values]
            elif len(dims) == len(values):
                pairs = list(zip(values, dims))
            else:
                continue

            for value, dim in pairs:
                business = dim.get("business_name")
                if not business or not value:
                    continue
                seen[(business, value)] = (
                    value, business, dim.get("table_name"), dim.get("column_name"),
                )

    return sorted(seen.values())


def values_by_dimension() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for value, business, _table, _column in _dimension_records():
        out.setdefault(business, [])
        if value not in out[business]:
            out[business].append(value)
    return {k: sorted(v) for k, v in sorted(out.items())}


def dimension_ids() -> Dict[str, int]:
    return {name: i + 1 for i, name in enumerate(sorted(values_by_dimension()))}


class RecordedValueProvider(StaticDimensionValueProvider):
    """Candidate provider over the recorded universe."""

    def __init__(self):
        super().__init__(
            values_by_dimension=values_by_dimension(),
            provenance=PROVENANCE_RECORDED,
        )
        self._tables = {
            (business, value): (table, column)
            for value, business, table, column in _dimension_records()
        }

    def get_candidates(self, dimension, phrase, context=None):
        from dataclasses import replace
        out = []
        for candidate in super().get_candidates(dimension, phrase, context):
            table, column = self._tables.get(
                (candidate.dimension, candidate.value), (None, None)
            )
            out.append(replace(candidate, table_name=table, column_name=column))
        return out


def cached_dimension_values() -> List[CachedDimensionValue]:
    """
    The SAME universe, shaped for the legacy matcher index.

    Built here so both paths see identical data; any difference the harness
    reports is then a difference in resolution behaviour, not in inputs.
    """
    ids = dimension_ids()
    out = []
    for value, business, table, column in _dimension_records():
        norm = normalize_for_matching(value)
        tokens = norm.split()
        singulars = [SingularPluralMatcher._to_singular(t) for t in tokens]
        out.append(
            CachedDimensionValue(
                semantic_dimension_id=ids.get(business, 0),
                business_name=business,
                table_name=table,
                column_name=column,
                value=value,
                normalized_value=norm,
                runtime_stored_norm=norm,
                runtime_stored_tokens=tokens,
                runtime_stored_singulars=singulars,
                runtime_raw_norm=norm,
                runtime_raw_tokens=tokens,
                runtime_raw_singulars=singulars,
            )
        )
    return out


def summary() -> str:
    vbd = values_by_dimension()
    total = sum(len(v) for v in vbd.values())
    return "recorded universe: %d values across %d dimensions (%s)" % (
        total, len(vbd), ", ".join(sorted(vbd)),
    )
