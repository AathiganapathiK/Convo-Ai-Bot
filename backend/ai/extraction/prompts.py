"""
Gate 4 Step 25 - the extraction prompt.

ONE CALL, CLOSED VOCABULARY

The prompt asks for every slot at once and constrains each enum field to the
exact members defined in semantic/models/semantic_plan.py. The allowed values
are rendered from the enums themselves rather than typed out here, so adding a
mode in Gate 8 cannot leave this prompt describing a stale set.

THE PART THAT MATTERS MOST

"Top 5 products whose sales are reducing last quarter" is the canonical case,
and the failure it represents is subtle enough to be worth spelling out in the
prompt rather than hoping the model infers it. There are two different
questions here:

    rank by the metric   -> the five products with the smallest sales
    rank by the change   -> the five products whose sales fell the most

The user asked the second. Answering the first returns five products that may
all be growing, which is a confident answer to a question nobody asked. So
RankMeasure is given its own worked section, and the model is told that a word
describing motion ("reducing", "declining", "dropping", "growing") makes the
measure CHANGE, while a word describing size ("smallest", "lowest", "biggest")
makes it ABSOLUTE.

WHY EVIDENCE IS REQUESTED

Every filled slot must come back with the user's own words that justify it.
This is not decoration. It is the cheapest available check on fabrication: a
model that invents a benchmark has to invent a quote to go with it, and a quote
that does not appear in the question is caught deterministically by the
validator without a second model call.
"""

from typing import List, Optional

from semantic.models.semantic_plan import (
    AnalysisMode,
    BenchmarkType,
    OutputFormat,
    RankDirection,
    RankMeasure,
)


def _members(enum_cls) -> str:
    return " | ".join(m.value for m in enum_cls)


_MODE_GUIDE = """\
DESCRIPTIVE  - what is the number. "Total sales", "sales by brand".
COMPARISON   - one period or group measured against another. "This year vs last".
TREND        - movement over consecutive periods. "Sales trend", "month by month".
RANKING      - an ordered subset. "Top 5", "worst performing", "bottom 10".
DIAGNOSTIC   - why did something happen. "Why did sales drop in Chennai?"
PRESCRIPTIVE - what should be done. "How do I improve dhoti sales?"
"""

_MEASURE_GUIDE = """\
ABSOLUTE   - order by the size of the metric itself.
             Cues: highest, lowest, biggest, smallest, largest, most, least.
             "Top 5 products by sales"        -> ABSOLUTE
CHANGE     - order by how much the metric moved between two periods.
             Cues: reducing, declining, falling, dropping, shrinking, growing,
                   rising, increasing, improved, worsened, gained, lost.
             "Top 5 products whose sales are reducing" -> CHANGE
CHANGE_PCT - order by the percentage movement, when the user says percent,
             percentage, %, or "fastest growing/declining".
             "Fastest declining brands by %"  -> CHANGE_PCT

Read the noun the ordering word attaches to. "Lowest sales" orders on sales,
so ABSOLUTE. "Sales are reducing" describes sales moving, so CHANGE. If the
question describes movement, the measure is never ABSOLUTE.
"""

_DIRECTION_GUIDE = """\
DESC - the largest first. Cues: top, highest, best, most, biggest, growing.
ASC  - the smallest first. Cues: bottom, lowest, worst, least, smallest.

With measure=CHANGE, direction describes the change, not the metric:
  "whose sales are reducing"  -> the most negative change first -> ASC
  "fastest growing"           -> the most positive change first -> DESC
"""

_BENCHMARK_GUIDE = """\
TARGET       - against a goal or target.
PEER_AVERAGE - against an average of comparable things.
FORECAST     - against a forecast or projection.
PLAN         - against a plan or budget.

Only set this when the user names such a comparison. A period-against-period
comparison ("vs last year") is NOT a benchmark - it belongs in comparison_period.
"""


def build_extraction_prompt(
    question: str,
    metric_names: Optional[List[str]] = None,
    dimension_names: Optional[List[str]] = None,
    history_summary: str = "",
) -> str:
    """
    The single extraction prompt.

    Configured metric and dimension names are supplied as a closed list so the
    model chooses from this business's vocabulary rather than inventing a field.
    They are advisory at this stage: the validator in slot_extractor.py drops
    anything not in the list, so a model that ignores the list cannot get a
    fabricated field into the plan.
    """
    metric_block = ", ".join(metric_names or []) or "(none configured)"
    dimension_block = ", ".join(dimension_names or []) or "(none configured)"

    history_block = ""
    if history_summary:
        history_block = (
            f"\nEARLIER IN THIS CONVERSATION\n{history_summary}\n"
            "Use this only to interpret a follow-up that omits something it "
            "already established. Never let it override what the user says now.\n"
        )

    return f"""\
You extract the structure of a business analytics question. You do not answer
it and you do not write SQL.

Return ONE JSON object and nothing else. No prose, no markdown fence.

ANALYSIS MODE (field "mode"), one of: {_members(AnalysisMode)}
{_MODE_GUIDE}
RANK DIRECTION (field "direction"), one of: {_members(RankDirection)}
{_DIRECTION_GUIDE}
RANK MEASURE (field "measure"), one of: {_members(RankMeasure)}
{_MEASURE_GUIDE}
BENCHMARK (field "benchmark"), one of: {_members(BenchmarkType)}
{_BENCHMARK_GUIDE}
OUTPUT FORMAT (field "output"), one of: {_members(OutputFormat)}
Set this only if the user asked for a specific presentation (a chart, a table).

CONFIGURED MEASURES FOR THIS BUSINESS
{metric_block}

CONFIGURED GROUPINGS FOR THIS BUSINESS
{dimension_block}
{history_block}
RULES
1. Fill a field ONLY from what the user said. If the user did not say it, use
   null. Never fill a field with a reasonable default - something later in the
   pipeline is responsible for defaults and has to record them.
2. Choose metric_terms and dimension_terms from the configured lists above,
   copying the configured name exactly. If the user names something that is not
   in the lists, put it in "unknown_terms" instead. Do not map it to the
   nearest configured name.
3. direction, measure and top_n apply only when mode is RANKING. Leave them
   null otherwise.
4. For every field you fill, add the user's exact words that justify it to
   "evidence". Copy them from the question verbatim.
5. For every field you fill, give a confidence between 0 and 1 in "confidence".
   Use a low score when you are guessing. A guess marked as a guess is useful;
   a guess marked as certain is harmful.
6. time_period is the period asked about ("last quarter"). comparison_period is
   any second period it is measured against ("vs the year before"). Copy the
   user's wording; do not convert to dates.

SHAPE
{{
  "mode": null,
  "direction": null,
  "measure": null,
  "top_n": null,
  "benchmark": null,
  "output": null,
  "metric_terms": [],
  "dimension_terms": [],
  "unknown_terms": [],
  "time_period": null,
  "comparison_period": null,
  "evidence": {{}},
  "confidence": {{}}
}}

WORKED EXAMPLE
Question: Top 5 products whose sales are reducing last quarter
{{
  "mode": "RANKING",
  "direction": "ASC",
  "measure": "CHANGE",
  "top_n": 5,
  "benchmark": null,
  "output": null,
  "metric_terms": ["Sales"],
  "dimension_terms": ["Product"],
  "unknown_terms": [],
  "time_period": "last quarter",
  "comparison_period": null,
  "evidence": {{
    "mode": "Top 5",
    "direction": "reducing",
    "measure": "sales are reducing",
    "top_n": "Top 5",
    "metric": "sales",
    "dimension": "products",
    "time_period": "last quarter"
  }},
  "confidence": {{
    "mode": 0.97, "direction": 0.93, "measure": 0.92, "top_n": 0.99,
    "metric": 0.95, "dimension": 0.95, "time_period": 0.94
  }}
}}
The measure is CHANGE, not ABSOLUTE: the user asked which products are falling,
not which products are small.

QUESTION
{question}
"""


def build_escalation_prompt(
    question: str,
    weak_slots: List[str],
    first_pass: dict,
    metric_names: Optional[List[str]] = None,
    dimension_names: Optional[List[str]] = None,
) -> str:
    """
    The second-pass prompt, sent to the stronger model.

    Deliberately narrow: it shows the first reading and asks about the specific
    fields that were weak, rather than re-extracting everything. Re-extracting
    would let the stronger model disturb fields the fast model was certain
    about, which turns a targeted fix into an unreviewable rewrite.
    """
    metric_block = ", ".join(metric_names or []) or "(none configured)"
    dimension_block = ", ".join(dimension_names or []) or "(none configured)"
    slots = ", ".join(weak_slots)

    return f"""\
A first pass read this analytics question and was unsure about some fields.
Decide those fields only.

QUESTION
{question}

FIRST READING
{first_pass}

FIELDS TO DECIDE: {slots}

CONFIGURED MEASURES: {metric_block}
CONFIGURED GROUPINGS: {dimension_block}

{_MEASURE_GUIDE}
{_DIRECTION_GUIDE}
Return ONE JSON object holding only the listed fields, plus "evidence" and
"confidence" entries for each. Use null for any field the question genuinely
does not determine - saying "the user did not specify" is a correct answer and
is more useful than a guess.

{{"<field>": <value>, "evidence": {{}}, "confidence": {{}}}}
"""
