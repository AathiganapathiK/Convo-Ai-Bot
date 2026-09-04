"""
Gate 4 Step 23 - the router's vocabulary, read from the semantic layer.

WHY THIS EXISTS

The router's keyword lists in ai/intent_classifier.py were written against the
AdventureWorks demo database: reseller, salesperson, subcategory, orderdate,
unitprice. This customer sells dhotis, banians and shirtings. Not one of those
demo terms appears in their data, and not one of their terms appeared in the
router. Every routing decision was therefore being made on vocabulary that
described a different business.

The fix is not a better hardcoded list - it is to stop hardcoding. An
administrator already told us what this business calls things, twice over: once
in semantic_metrics/semantic_dimensions (business_name plus comma-separated
synonyms) and once in semantic_domains (business areas). That IS the routing
vocabulary. It changes when the configuration changes, which is exactly the
behaviour we want and exactly what a static list cannot do.

WHAT IS EXCLUDED, AND BY WHOM

Nothing here decides what to hide. The exclusion predicates come from
semantic.runtime_config_filter - metric_filter() and dimension_filter() - which
is Gate 3's single implementation of "what did the administrator switch off".
This module imports and concatenates them; it does not reimplement them and
does not add a second exclusion mechanism of its own.

That matters for a concrete reason. If an administrator excludes a duplicate
State column in the Semantic Control Center, and the router still carries
"state" as a routing keyword, the column is hidden from answers but still
steers the conversation. Exclusion has to reach the router or it is not really
exclusion.

CACHING

Vocabulary is read once per connection and held in a process-local dict. The
semantic configuration changes when an administrator saves, not when a user
asks a question, so a per-question query would be pure overhead. Callers that
mutate configuration call invalidate(connection_id); config_service does this
on confirm/reject/upsert. A missing invalidation shows up as stale routing
until restart, never as a wrong answer, because the resolver reads the database
directly and is not fed from this cache.

DEGRADATION

Every read is defensive in the same direction as runtime_config_filter: a
database without the Gate 2 tables yields an empty vocabulary rather than an
exception. An empty vocabulary makes the router fall through to its LLM stage,
which is the pre-Gate-4 behaviour. The chat feature never breaks because
configuration is missing.
"""

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from sqlalchemy import text

from database import engine
from semantic import runtime_config_filter

logger = logging.getLogger(__name__)


# Terms this short are not evidence of anything. "id", "no", "dt" appear as
# business names on poorly named columns and would route half of English into
# the analytical pipeline. Three characters is the shortest real business term
# observed in this registry ("qty", "amt", "due").
_MIN_TERM_LENGTH = 3


# Business names that are too generic to route on by themselves. These are real
# configured names in this registry, but a question containing only one of them
# is not yet evidence of an analytical question - "what is the name for this?"
# is not a data question. They stay in the vocabulary for display (step 24) and
# are excluded only from routing evidence.
_NON_ROUTING_TERMS = {
    "name", "code", "type", "id", "key", "flag", "number", "description",
    "date", "value", "status", "amount", "total", "count", "data",
}


@dataclass(frozen=True)
class VocabularyTerm:
    """
    One way a business user might name one configured object.

    `term` is the lowercased surface form to match on. `canonical` is the
    configured business_name it belongs to, so the router can report which
    configured object it matched rather than just that something matched.
    """
    term: str
    canonical: str
    kind: str          # "metric" | "dimension" | "domain"
    technical_name: str = ""
    table_name: str = ""
    is_synonym: bool = False


@dataclass
class Vocabulary:
    """
    Everything the router and the metadata answerer know about one connection.

    Kept as plain lists rather than a search structure on purpose: this registry
    holds 20 metrics and 76 dimensions, and a linear scan over a few hundred
    terms is far below the cost of the database round trip that produced it.
    """
    connection_id: str = ""
    metrics: List[dict] = field(default_factory=list)
    dimensions: List[dict] = field(default_factory=list)
    domains: List[dict] = field(default_factory=list)
    terms: List[VocabularyTerm] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.metrics and not self.dimensions

    def metric_names(self) -> List[str]:
        return [m["business_name"] for m in self.metrics if m.get("business_name")]

    def dimension_names(self) -> List[str]:
        return [d["business_name"] for d in self.dimensions if d.get("business_name")]

    def domain_names(self) -> List[str]:
        return [d["business_name"] for d in self.domains if d.get("business_name")]

    def is_generic(self, entry: "VocabularyTerm") -> bool:
        """
        Whether a term is too common to be evidence on its own.

        Note "on its own". These are real configured names - this registry
        genuinely has a metric called Amount - so they are matched and reported
        like any other. What they cannot do is carry a routing decision by
        themselves, because "what is the name for this" is not a data question.
        Combined with an analytical operation, or with a second configured term,
        they count normally.
        """
        return entry.term in _NON_ROUTING_TERMS

    def specific_matches(self, question: str) -> List[VocabularyTerm]:
        """Matches excluding the generic terms. Evidence that stands alone."""
        return [m for m in self.find_matches(question) if not self.is_generic(m)]

    def find_matches(self, question: str) -> List[VocabularyTerm]:
        """
        Configured terms appearing in `question` as whole words.

        Whole-word matching only. Substring matching is what made the old router
        classify "stopped" as a ranking question because it contains "top", and
        the same trap applies here: the dimension "Size" must not match
        "capsized". Multi-word terms are matched as phrases.
        """
        if not question:
            return []

        haystack = _normalize(question)
        hits: List[VocabularyTerm] = []
        seen: Set[str] = set()

        for entry in self.terms:
            if entry.term in seen:
                continue
            if _contains_whole_term(haystack, entry.term):
                hits.append(entry)
                seen.add(entry.term)

        # Longest first, so a report reads "Cotton Pants" before "Cotton".
        hits.sort(key=lambda t: (-len(t.term), t.term))
        return hits


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _normalize(value: str) -> str:
    """Lowercase, punctuation to spaces, whitespace collapsed."""
    if not value:
        return ""
    lowered = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(lowered.split())


def _contains_whole_term(haystack: str, term: str) -> bool:
    """
    Whole-word/phrase containment on two already-normalized strings.

    Both sides are normalized to single-spaced tokens, so a space-padded
    substring test is exact and avoids building a regex per term per question.
    """
    if not term or not haystack:
        return False
    return f" {term} " in f" {haystack} "


def _split_synonyms(raw: Optional[str]) -> List[str]:
    """
    Comma-separated synonyms, the convention used across the semantic tables.

    Blank entries are dropped rather than stored as empty terms, which would
    otherwise match every question.
    """
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _accept_term(value: str) -> bool:
    return len(value) >= _MIN_TERM_LENGTH


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

_cache: Dict[str, Vocabulary] = {}
_cache_lock = threading.Lock()


def _load_metrics(conn, connection_id: str) -> List[dict]:
    """
    Active, non-excluded metrics.

    The exclusion predicate is appended from runtime_config_filter rather than
    written inline, so that a database predating migration 004 - where
    is_excluded does not exist - yields an empty fragment instead of a query
    that raises on every question.
    """
    query = f"""
        SELECT metric_name, business_name, table_name, column_name,
               aggregation_type, synonyms, description
        FROM semantic_metrics
        WHERE connection_id = :connection_id
          AND is_active = 1
          {runtime_config_filter.metric_filter()}
    """
    rows = conn.execute(text(query), {"connection_id": connection_id}).fetchall()
    return [
        {
            "metric_name": r[0],
            "business_name": r[1],
            "table_name": r[2],
            "column_name": r[3],
            "aggregation_type": r[4],
            "synonyms": r[5],
            "description": r[6],
        }
        for r in rows
    ]


def _load_dimensions(conn, connection_id: str) -> List[dict]:
    """
    Active, non-excluded, non-INTERNAL dimensions.

    dimension_filter() supplies both predicates. INTERNAL is excluded there
    because config_schema defines the role as "exists but is not offered to
    business users" - a load timestamp marked INTERNAL must not become a
    routing keyword or appear in the answer to "what can I ask?".
    """
    query = f"""
        SELECT dimension_name, business_name, table_name, column_name,
               synonyms, semantic_category, description
        FROM semantic_dimensions
        WHERE connection_id = :connection_id
          AND is_active = 1
          {runtime_config_filter.dimension_filter()}
    """
    rows = conn.execute(text(query), {"connection_id": connection_id}).fetchall()
    return [
        {
            "dimension_name": r[0],
            "business_name": r[1],
            "table_name": r[2],
            "column_name": r[3],
            "synonyms": r[4],
            "semantic_category": r[5],
            "description": r[6],
        }
        for r in rows
    ]


def _load_domains(conn, connection_id: str) -> List[dict]:
    """
    Business areas, when the table exists.

    semantic_domains arrived with migration 004. It is queried separately and
    guarded separately so that its absence costs the domain list only, leaving
    metrics and dimensions - the parts the router actually needs - intact.
    """
    try:
        rows = conn.execute(
            text("""
                SELECT domain_name, business_name, synonyms, description
                FROM semantic_domains
                WHERE connection_id = :connection_id
                  AND is_active = 1
                ORDER BY business_name
            """),
            {"connection_id": connection_id},
        ).fetchall()
    except Exception as exc:
        logger.warning(
            "semantic_domains unavailable (%s); continuing without domains.",
            str(exc).splitlines()[0][:160],
        )
        return []

    return [
        {
            "domain_name": r[0],
            "business_name": r[1],
            "synonyms": r[2],
            "description": r[3],
        }
        for r in rows
    ]


def _build_terms(
    metrics: List[dict],
    dimensions: List[dict],
    domains: List[dict],
) -> List[VocabularyTerm]:
    """
    Flatten configured objects into the surface forms a user might type.

    Both the business name and every synonym become terms. The technical name
    is deliberately NOT a term: column names like CY, PAMT and PYTD are not
    words a business user types, and admitting them would route "cy" inside
    other text and add noise for no recall.
    """
    terms: List[VocabularyTerm] = []
    seen: Set[str] = set()

    def add(raw: str, canonical: str, kind: str, technical: str, table: str, is_syn: bool):
        normalized = _normalize(raw)
        if not normalized or not _accept_term(normalized):
            return
        key = f"{kind}:{normalized}"
        if key in seen:
            return
        seen.add(key)
        terms.append(
            VocabularyTerm(
                term=normalized,
                canonical=canonical or raw,
                kind=kind,
                technical_name=technical or "",
                table_name=table or "",
                is_synonym=is_syn,
            )
        )

    for m in metrics:
        canonical = m.get("business_name") or m.get("metric_name") or ""
        add(canonical, canonical, "metric", m.get("metric_name", ""), m.get("table_name", ""), False)
        for syn in _split_synonyms(m.get("synonyms")):
            add(syn, canonical, "metric", m.get("metric_name", ""), m.get("table_name", ""), True)

    for d in dimensions:
        canonical = d.get("business_name") or d.get("dimension_name") or ""
        add(canonical, canonical, "dimension", d.get("dimension_name", ""), d.get("table_name", ""), False)
        for syn in _split_synonyms(d.get("synonyms")):
            add(syn, canonical, "dimension", d.get("dimension_name", ""), d.get("table_name", ""), True)

    for dom in domains:
        canonical = dom.get("business_name") or dom.get("domain_name") or ""
        add(canonical, canonical, "domain", "", "", False)
        for syn in _split_synonyms(dom.get("synonyms")):
            add(syn, canonical, "domain", "", "", True)

    return terms


def get_vocabulary(connection_id: str, refresh: bool = False) -> Vocabulary:
    """
    The routing vocabulary for one connection, cached per process.

    Returns an empty Vocabulary rather than raising when the connection has no
    configuration or the database is unreachable. An empty vocabulary is a
    meaningful answer - it means this connection cannot yet route on business
    terms - and the router handles it by escalating to the LLM stage.
    """
    if not connection_id:
        return Vocabulary()

    key = str(connection_id)

    if not refresh:
        cached = _cache.get(key)
        if cached is not None:
            return cached

    try:
        with engine.connect() as conn:
            metrics = _load_metrics(conn, key)
            dimensions = _load_dimensions(conn, key)
            domains = _load_domains(conn, key)
    except Exception as exc:
        logger.warning(
            "Could not load routing vocabulary for %s (%s); "
            "router will fall back to its language stage.",
            key,
            str(exc).splitlines()[0][:160],
        )
        return Vocabulary(connection_id=key)

    vocabulary = Vocabulary(
        connection_id=key,
        metrics=metrics,
        dimensions=dimensions,
        domains=domains,
        terms=_build_terms(metrics, dimensions, domains),
    )

    with _cache_lock:
        _cache[key] = vocabulary

    logger.info(
        "Routing vocabulary loaded for %s: %d metrics, %d dimensions, "
        "%d domains, %d terms.",
        key, len(metrics), len(dimensions), len(domains), len(vocabulary.terms),
    )
    return vocabulary


def invalidate(connection_id: Optional[str] = None) -> None:
    """
    Drop cached vocabulary after a configuration change.

    Called with no argument this clears every connection, which is what a
    migration or a bulk confirm should do.
    """
    with _cache_lock:
        if connection_id is None:
            _cache.clear()
        else:
            _cache.pop(str(connection_id), None)


def prime(connection_id: str, vocabulary: Vocabulary) -> None:
    """
    Install a vocabulary directly. For tests, which have no database.

    Kept explicit rather than letting tests reach into _cache, so the cache
    shape stays private and a test that primes is obvious in review.
    """
    with _cache_lock:
        _cache[str(connection_id)] = vocabulary


# ---------------------------------------------------------------------------
# Step 24 - answering questions about the data
# ---------------------------------------------------------------------------

def describe_capabilities(connection_id: str, question: str = "") -> Optional[str]:
    """
    Answer a metadata question from configuration alone. No SQL, ever.

    The whole point of the METADATA destination is that "what can I ask?" has a
    correct answer that lives in the semantic registry, and generating SQL to
    discover it - or letting a general chat model invent plausible-sounding
    field names - produces confident fiction. Everything returned here is a
    configured business_name.

    Returns None when there is no configuration to describe, which the caller
    must treat as "cannot answer" rather than substituting a guess.
    """
    vocabulary = get_vocabulary(connection_id)

    if vocabulary.is_empty:
        return None

    focus = _metadata_focus(question)
    lines: List[str] = []

    if focus in ("all", "metric"):
        names = sorted(set(vocabulary.metric_names()))
        if names:
            lines.append(
                "Measures I can report on: " + ", ".join(names) + "."
            )

    if focus in ("all", "dimension"):
        names = sorted(set(vocabulary.dimension_names()))
        if names:
            shown = names[:40]
            suffix = "" if len(names) == len(shown) else f", and {len(names) - len(shown)} more"
            lines.append(
                "Ways I can break those down: " + ", ".join(shown) + suffix + "."
            )

    if focus in ("all", "domain"):
        names = sorted(set(vocabulary.domain_names()))
        if names:
            lines.append("Business areas configured: " + ", ".join(names) + ".")

    if not lines:
        return None

    if focus == "all":
        lines.append(
            "Ask for any of those by name - for example a measure on its own, "
            "or a measure broken down by one of the groupings above."
        )

    return "\n".join(lines)


def check_coverage(connection_id: str, term: str) -> Optional[bool]:
    """
    Whether a named thing is configured. For "do you track returns?".

    Returns True/False when there is a vocabulary to check against, and None
    when there is not - so the caller can say "I cannot tell" instead of
    reporting a confident False that only means "nothing is configured".
    """
    vocabulary = get_vocabulary(connection_id)
    if vocabulary.is_empty:
        return None

    normalized = _normalize(term)
    if not normalized:
        return None

    for entry in vocabulary.terms:
        if entry.term == normalized or _contains_whole_term(entry.term, normalized):
            return True
    return False


_METADATA_FOCUS_CUES = (
    ("metric", ("metric", "metrics", "measure", "measures", "kpi", "kpis")),
    ("dimension", ("dimension", "dimensions", "field", "fields", "column",
                   "columns", "group by", "grouping", "groupings", "breakdown",
                   "break down", "split by", "attribute", "attributes")),
    ("domain", ("domain", "domains", "area", "areas", "subject area", "module", "modules")),
)


def _metadata_focus(question: str) -> str:
    """
    Which part of the registry a metadata question is about.

    "What metrics do you have" should not recite 76 dimensions. Defaults to
    "all", which is the right answer for the open "what can I ask?".
    """
    haystack = _normalize(question)
    if not haystack:
        return "all"

    for focus, cues in _METADATA_FOCUS_CUES:
        for cue in cues:
            if _contains_whole_term(haystack, _normalize(cue)):
                return focus

    return "all"
