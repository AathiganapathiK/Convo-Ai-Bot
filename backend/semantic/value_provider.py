"""
Where candidate dimension values come from.

The point of this module is a seam. Everything above it - phrase-scoped
resolution, candidate scoring, the ambiguity decision - must be testable and
correct without a database, and must not care whether the values it is ranking
came from SQL Server, a cache, or a test fixture. So the higher layers depend
on the DimensionValueProvider contract below and never on a concrete source.

The rule that makes this worth having: a candidate is a real value that some
provider vouched for. Every candidate carries its `provenance`, and no code
path may construct one from model output. The extractor says which words to
look up; only a provider says what exists.

Swapping MockDimensionValueProvider (tests) for DbDimensionValueProvider
(production) changes nothing above this file.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def normalize_for_matching(text: str) -> str:
    """
    Lowercase alphanumeric words, punctuation removed.

    The existing DimensionValueResolver._normalize_text lowercases and collapses
    whitespace but keeps punctuation, so "Mumbai," normalizes to "mumbai," and
    never equals the stored "MUMBAI". That is a real weakness in the legacy
    path, but fixing it there would change matcher behaviour this step is not
    allowed to touch. This function is used ONLY by the new provider/scoring
    path, where a trailing comma has never been allowed to cost a match.
    """
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# Provenance values. A candidate that cannot name where it came from is not a
# candidate; there is deliberately no member here meaning "the model said so".
PROVENANCE_DB = "db/semantic-value-index"
PROVENANCE_MOCK = "mock/test/provider-generated-from-fixture"


@dataclass(frozen=True)
class ValueCandidate:
    """
    One real value a provider vouches for, as a possible reading of a phrase.

    `value` is the stored form and is what any downstream consumer must use -
    never the phrase the user typed and never the spelling a model produced.
    """
    value: str
    normalized_value: str
    dimension: str
    provenance: str
    dimension_id: Optional[int] = None
    table_name: Optional[str] = None
    column_name: Optional[str] = None

    # Confidence from an existing matcher, when the provider had one to pass
    # on. None means "no matcher opinion", which the scorer treats as absent
    # evidence rather than as zero confidence.
    matcher_confidence: Optional[float] = None
    match_type: Optional[str] = None

    def __post_init__(self):
        if not self.provenance:
            raise ValueError("ValueCandidate requires provenance")


class DimensionValueProvider:
    """
    The contract. Implementations return real values only.

    `get_candidates` is deliberately given the phrase AND the dimension AND the
    surrounding context: the phrase says what to look for, the dimension narrows
    where to look when the user qualified it, and the context lets a provider
    that can use it (an indexed one) prefilter. A provider may ignore context;
    it may never invent a value because of it.
    """

    def get_candidates(
        self,
        dimension: Optional[str],
        phrase: str,
        context: Optional[dict] = None,
    ) -> List[ValueCandidate]:
        raise NotImplementedError

    def dimensions(self) -> List[str]:
        """Configured dimension names this provider can serve."""
        raise NotImplementedError


class DbDimensionValueProvider(DimensionValueProvider):
    """
    Production adapter over the existing cached value index.

    Deliberately thin: it reuses DimensionValueResolver._load_dimension_values,
    which is already the single place real values are read and cached, rather
    than opening a second path to the database. Candidate filtering here is
    only the cheap containment prefilter - real scoring belongs to the scorer,
    which is shared with the mock provider so both are ranked identically.
    """

    def __init__(self, resolver=None, connection_id: Optional[str] = None):
        self._resolver = resolver
        self._connection_id = connection_id

    def _values(self):
        from semantic.dimension_value_resolver import DimensionValueResolver
        resolver = self._resolver or DimensionValueResolver()
        return resolver._load_dimension_values(self._connection_id)

    def dimensions(self) -> List[str]:
        return sorted({(v.business_name or "") for v in self._values() if v.business_name})

    def get_candidates(self, dimension, phrase, context=None) -> List[ValueCandidate]:
        wanted = (dimension or "").strip().lower() or None
        phrase_norm = normalize_for_matching(phrase)
        phrase_tokens = set(phrase_norm.split())
        if not phrase_tokens:
            return []

        out: List[ValueCandidate] = []
        for v in self._values():
            if wanted and (v.business_name or "").strip().lower() != wanted:
                continue
            # Cheap prefilter only: share at least one token with the phrase.
            # Anything finer is the scorer's job, not the provider's.
            if not phrase_tokens & set(normalize_for_matching(v.value).split()):
                continue
            out.append(
                ValueCandidate(
                    value=v.value,
                    normalized_value=normalize_for_matching(v.value),
                    dimension=v.business_name,
                    provenance=PROVENANCE_DB,
                    dimension_id=v.semantic_dimension_id,
                    table_name=v.table_name,
                    column_name=v.column_name,
                )
            )
        return out


@dataclass
class StaticDimensionValueProvider(DimensionValueProvider):
    """
    A provider backed by an explicit {dimension: [values]} mapping.

    This is the base the test fixture builds on. It lives here, beside the
    contract, so the contract has a reference implementation that is exercised
    by the same tests as the real one - but it holds NO data of its own. All
    values must be handed to it, which is what keeps fixture data out of the
    production configuration.
    """
    values_by_dimension: Dict[str, List[str]] = field(default_factory=dict)
    provenance: str = PROVENANCE_MOCK

    def dimensions(self) -> List[str]:
        return sorted(self.values_by_dimension)

    def _dimension_id(self, dimension: str) -> int:
        """
        A stable, distinct id per dimension name.

        Not decoration. Downstream consolidation keys candidates on
        (dimension_id, normalized_value), so a provider that leaves the id
        unset makes CHENNAI-the-City and CHENNAI-the-District look like one
        candidate and silently destroys genuine cross-dimension ambiguity.
        Real dimensions have distinct ids; a provider standing in for them
        must too.
        """
        return sorted(self.values_by_dimension).index(dimension) + 1

    def get_candidates(self, dimension, phrase, context=None) -> List[ValueCandidate]:
        phrase_norm = normalize_for_matching(phrase)
        phrase_tokens = set(phrase_norm.split())
        if not phrase_tokens:
            return []

        wanted = (dimension or "").strip().lower() or None
        out: List[ValueCandidate] = []

        for dim, values in self.values_by_dimension.items():
            if wanted and dim.strip().lower() != wanted:
                continue
            for raw in values:
                norm = normalize_for_matching(raw)
                if not phrase_tokens & set(norm.split()):
                    # Keep near-spellings the token filter would lose
                    # ("coimbator" vs "coimbatore"); the scorer decides whether
                    # they are good enough, this only decides they are worth
                    # looking at.
                    if not _near(phrase_norm, norm):
                        continue
                out.append(
                    ValueCandidate(
                        value=raw,
                        normalized_value=norm,
                        dimension=dim,
                        provenance=self.provenance,
                        dimension_id=self._dimension_id(dim),
                    )
                )
        return out


def _near(a: str, b: str) -> bool:
    """Cheap prefix-similarity gate for the static provider's prefilter."""
    if not a or not b:
        return False
    for at in a.split():
        for bt in b.split():
            if at == bt:
                return True
            shorter, longer = (at, bt) if len(at) <= len(bt) else (bt, at)
            if len(shorter) >= 4 and longer.startswith(shorter[:max(4, len(shorter) - 1)]):
                return True
    return False
