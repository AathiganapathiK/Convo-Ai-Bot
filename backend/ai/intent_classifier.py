"""
ai/intent_classifier.py

Two-stage intent classifier.

Stage 1 — Keyword routing (zero LLM cost):
    If the question contains any known business/data keyword,
    immediately return ANALYTICS without calling the LLM.

Stage 2 — LLM fallback:
    Only if no keyword matched, call the Groq LLM to decide
    between ANALYTICS and GENERAL.

Returns: "ANALYTICS" or "GENERAL"
"""

import logging
import os
import re

from ai.providers.provider_factory import (
    ProviderFactory
)

from services.model_routing_service import (
    ModelRoutingService
)

from services.llm_execution_service import (
    LLMExecutionService
)

logger = logging.getLogger(__name__)

def get_intent_provider():

    provider_config = (
        ModelRoutingService
        .get_model_for_purpose(
            "intent"
        )
    )

    provider = (
        ProviderFactory
        .get_provider(
            provider_config[
                "provider_type"
            ]
        )
    )

    return (
        provider,
        provider_config[
            "model_name"
        ]
    )


# ---------------------------------------------------------------------------
# Stage 1: Keyword list (AdventureWorks business domain)
# ---------------------------------------------------------------------------

# Each entry is a whole-word pattern (case-insensitive).
# Add new terms here without touching any other code.
_ANALYTICS_KEYWORDS: list[str] = [
    # AdventureWorks entities
    "product", "products",
    "region", "regions",
    "reseller", "resellers",
    "salesperson",
    "salesperson region",
    "target", "targets",
    "category", "subcategory",
    "city", "cities", "state", "states", "country", "countries",

    # Financial metrics
    "sales", "revenue", "profit", "cost", "quantity",
    "unitprice", "unit price", "price",

    # Temporal fields
    "orderdate", "order date", "month", "year", "quarter", "weekly", "daily",

    # Analytics operations
    "top", "bottom", "highest", "lowest",
    "average", "avg", "sum", "total", "count",
    "trend", "growth", "compare", "comparison",
    "analysis", "analytics", "metric", "metrics",
    "report", "reports",

    # Query intent words
    "show", "list", "find", "give", "get",
    "how many", "how much", "which", "what is",
    "breakdown", "distribution", "performance",
    "ranking", "rank", "best", "worst",
]

# Pre-compile a single regex for efficiency:
# \b word-boundary ensures "top" doesn't match "laptop"
_KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in _ANALYTICS_KEYWORDS) + r")\b",
    flags=re.IGNORECASE,
)
# Strong signals — one match = ANALYTICS
_STRONG_KEYWORDS = [
    "revenue", "profit", "sales", "cost", "unitprice",
    "orderdate", "reseller", "salesperson", "subcategory",
    "top", "bottom", "highest", "lowest", "ranking",
    "trend", "growth", "breakdown", "distribution", "performance",
    "city", "cities", "state", "states", "country", "countries",
]

# Weak signals — need 2+ matches to classify as ANALYTICS
_WEAK_KEYWORDS = [
    "product", "products", "region", "target",
    "average", "avg", "sum", "total", "count",
    "show", "list", "find", "get", "which", "what is",
    "report", "metric", "analysis",
    "month", "year", "quarter",
]

from typing import Optional

def _keyword_stage(question: str) -> Optional[str]:
    q = question.lower()
    strong_hit = any(re.search(r'\b' + re.escape(kw) + r'\b', q) for kw in _STRONG_KEYWORDS)
    if strong_hit:
        return "ANALYTICS"
    
    weak_hits = sum(1 for kw in _WEAK_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', q))
    if weak_hits >= 2:
        return "ANALYTICS"
    
    return None


# ---------------------------------------------------------------------------
# Stage 2: LLM fallback
# ---------------------------------------------------------------------------

_LLM_PROMPT = """\
Classify the user request.Return ONLY one word — either ANALYTICS or GENERAL.
ANALYTICS:
- Sales analysis, revenue, cost, profit
- Product, region, reseller, salesperson queries
- Reports, metrics, trends, business data
GENERAL:
- Greetings, casual conversation
- Help requests, system capability questions
- Anything not related to business data

Question:{question}
"""


def _llm_stage(question: str, company_id: Optional[str] = None) -> str:
    """
    Stage 2: Groq LLM classifier fallback.
    Returns "ANALYTICS" or "GENERAL".
    """
    provider, model_name = (
        get_intent_provider()
    )

    response = (
        LLMExecutionService.execute(
            purpose="intent",

            messages=[
                {
                    "role": "user",
                    "content":
                        _LLM_PROMPT.format(
                            question=question
                        )
                }
            ],
            company_id=company_id
        )
    )

    raw = ""
    if response and getattr(response, "choices", None):
        choice = response.choices[0]
        if choice and getattr(choice, "message", None):
            message = choice.message
            if message and getattr(message, "content", None) is not None:
                val = message.content
                if val is not None:
                    raw = val.strip().upper()

    intent = "ANALYTICS" if raw.startswith("ANALYTICS") else "GENERAL"

    logger.info(
        "Intent | question=%r | method=LLM | raw=%r | intent=%s",
        question,
        raw,
        intent,
    )

    return intent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_intent(question: str, company_id: Optional[str] = None) -> str:
    """
    Classify a user question as ANALYTICS or GENERAL.

    Uses a two-stage approach:
        Stage 1 — keyword matching (instant, zero cost).
        Stage 2 — LLM classification (only if Stage 1 misses).

    Returns "ANALYTICS" or "GENERAL".
    """
    # Stage 1: fast keyword check
    result = _keyword_stage(question)
    if result:
        return result

    # Stage 2: LLM fallback
    logger.info(
        "Intent | question=%r | no keyword match, escalating to LLM.",
        question,
    )
    return _llm_stage(question, company_id)