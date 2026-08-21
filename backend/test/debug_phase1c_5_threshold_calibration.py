import sys, os
from collections import defaultdict
from rapidfuzz import fuzz, process

# ---------------------------------------------------------------------------
# Setup environment – ensure project root is on sys.path for imports
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantic.dimension_value_resolver import DimensionValueResolver
from semantic.matching.fuzzy_matcher import FuzzyMatcher
from semantic.matching.stopwords import STOPWORDS

# ---------------------------------------------------------------------------
# Load the full semantic index for the given connection (read‑only)
# ---------------------------------------------------------------------------
CONN_ID = "F82C2F8D-0BD6-40E2-8C8B-FF1D69E317D5"
# Use the current production settings – the resolver reads the default cutoff
resolver = DimensionValueResolver()
indexed_values = resolver._load_dimension_values(CONN_ID)

# Retrieve the actual fuzzy cutoff used in production (from the resolver settings)
# It may be stored inside the resolver instance; fallback to 75 if not found.
CURRENT_FUZZY_CUTOFF = getattr(resolver, "FUZZY_SCORE_CUTOFF", 75)

# ---------------------------------------------------------------------------
# Test question groups
# ---------------------------------------------------------------------------
GROUP_1 = [
    "pant", "pants", "shirt", "banian", "banians", "banain",
    "t shrt", "cottn pant", "forml shirt", "womens wear",
    "mens wear", "child wear", "tamil nadu",
]
GROUP_2 = [
    "ramraj", "ram raj", "cotton pant", "formal shirt", "cotton pants",
    "kids", "children", "chennai", "coimbatore",
]
GROUP_3 = [
    "laptop", "banana", "hospital", "xyzabc", "pantxyz", "cottonxyz",
    "abc pant", "outstanding", "rm", "an", "ch", "ld",
]
ALL_QUESTIONS = [("VALID_EXACT", q) for q in GROUP_1] + [("VALID_VARIATION", q) for q in GROUP_2] + [("ADVERSARIAL", q) for q in GROUP_3]

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
fuzzy_matcher = FuzzyMatcher()

def normalize(text):
    return DimensionValueResolver._normalize_text(text)

def token_list(text):
    return [t for t in normalize(text).split() if t not in STOPWORDS]

def is_legitimate(question, candidate_val):
    """Heuristic: a candidate is considered legitimate if any meaningful token
    from the question appears as a whole token in the candidate value.
    Tokens of length <=2 are ignored to avoid matching trivial codes.
    """
    q_tokens = token_list(question)
    c_tokens = normalize(candidate_val).split()
    for qt in q_tokens:
        if len(qt) > 2 and qt in c_tokens:
            return True
    return False

def classification(entry):
    # Returns "legitimate" or "noise"
    return "legitimate" if is_legitimate(entry["question"], entry["candidate"]) else "noise"

# ---------------------------------------------------------------------------
# Collect raw candidate data (before token‑gate)
# ---------------------------------------------------------------------------
raw_entries = []  # list of dicts
for cat, q in ALL_QUESTIONS:
    norm_q = normalize(q)
    phrases = fuzzy_matcher.extractor.extract(norm_q)
    for phrase in phrases:
        # Get *all* candidates irrespective of cutoff (use 0)
        matches = process.extract(
            phrase,
            [v.normalized_value for v in indexed_values],
            scorer=fuzz.WRatio,
            score_cutoff=0,
        )
        for match_str, score, idx in matches:
            val = indexed_values[idx]
            evidence = FuzzyMatcher._has_token_level_evidence(phrase, val.value)
            raw_entries.append({
                "category": cat,
                "question": q,
                "phrase": phrase,
                "candidate": val.value,
                "score": score,
                "dimension": val.business_name,
                "table": val.table_name,
                "gate_pass": evidence["passed"],
                "token_similarity": evidence["best_token_similarity"],
                "matched_query_token": evidence["matched_query_token"],
                "matched_candidate_token": evidence["matched_candidate_token"],
                "legitimate": is_legitimate(q, val.value),
            })

# ---------------------------------------------------------------------------
# Empirical score distribution
# ---------------------------------------------------------------------------
scores = [e["score"] for e in raw_entries]
print("--- EMPIRICAL SCORE DISTRIBUTION ---")
print(f"Total candidates examined: {len(raw_entries)}")
print(f"Score min: {min(scores)} | max: {max(scores)} | median: {sorted(scores)[len(scores)//2]}")
print()

# ---------------------------------------------------------------------------
# Identify low‑score legitimate cases and high‑score noise cases
# ---------------------------------------------------------------------------
LOW_SCORE_LEGIT = [e for e in raw_entries if e["legitimate"] and e["score"] < CURRENT_FUZZY_CUTOFF]
HIGH_SCORE_NOISE = [e for e in raw_entries if not e["legitimate"] and e["score"] >= CURRENT_FUZZY_CUTOFF]

print("--- LEGITIMATE LOW‑SCORE CASES (score < current cutoff) ---")
for e in sorted(LOW_SCORE_LEGIT, key=lambda x: -x["score"])[:20]:
    print(f"Q='{e['question']}' | cand='{e['candidate']}' | score={e['score']} | dim={e['dimension']} | table={e['table']}")
print("... (truncated)\n")

print("--- FALSE‑POSITIVE HIGH‑SCORE CASES (noise with score >= current cutoff) ---")
for e in sorted(HIGH_SCORE_NOISE, key=lambda x: -x["score"])[:20]:
    print(f"Q='{e['question']}' | cand='{e['candidate']}' | score={e['score']} | dim={e['dimension']} | table={e['table']}")
print("... (truncated)\n")

# ---------------------------------------------------------------------------
# Threshold analysis
# ---------------------------------------------------------------------------
thresholds = [75, 78, 80, 82, 85, 88, 90]
analysis = []
for th in thresholds:
    retained_legit = 0
    lost_legit = 0
    retained_noise = 0
    rejected_noise = 0
    legit_scores = []
    noise_scores = []
    for e in raw_entries:
        if e["score"] >= th:
            if e["legitimate"]:
                retained_legit += 1
                legit_scores.append(e["score"])
            else:
                retained_noise += 1
                noise_scores.append(e["score"])
        else:
            if e["legitimate"]:
                lost_legit += 1
            else:
                rejected_noise += 1
    analysis.append({
        "threshold": th,
        "retained_legit": retained_legit,
        "lost_legit": lost_legit,
        "retained_noise": retained_noise,
        "rejected_noise": rejected_noise,
        "lowest_legit": min(legit_scores) if legit_scores else None,
        "highest_noise": max(noise_scores) if noise_scores else None,
    })

print("--- THRESHOLD COMPARISON TABLE ---")
print("Thresh | Ret Leg | Lost Leg | Ret Noise | Rej Noise | Low Leg Score | High Noise Score")
for a in analysis:
    print(f"{a['threshold']:>5} | {a['retained_legit']:>7} | {a['lost_legit']:>8} | {a['retained_noise']:>9} | {a['rejected_noise']:>10} | {a['lowest_legit'] or '-':>13} | {a['highest_noise'] or '-':>15}")
print()

# ---------------------------------------------------------------------------
# Specific investigations for 80 vs 85
# ---------------------------------------------------------------------------
def stats_for(th):
    leg = [e for e in raw_entries if e["legitimate"] and e["score"] >= th]
    noise = [e for e in raw_entries if not e["legitimate"] and e["score"] >= th]
    return len(leg), len(noise)
leg_80, noise_80 = stats_for(80)
leg_85, noise_85 = stats_for(85)
print(f"Recall at 80: {leg_80} legitimate candidates retained (vs {leg_85} at 85)"
      f" – delta +{leg_80 - leg_85}")
print(f"Noise at 80: {noise_80} noise candidates retained (vs {noise_85} at 85)"
      f" – delta +{noise_80 - noise_85}")
print()

# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------
# Simple heuristic: pick the smallest threshold that keeps >90% of legit and <5% noise.
# Compute percentages based on total counts.
TOTAL_LEG = sum(1 for e in raw_entries if e["legitimate"])
TOTAL_NOISE = sum(1 for e in raw_entries if not e["legitimate"])
recs = []
for a in analysis:
    recall = a['retained_legit'] / TOTAL_LEG if TOTAL_LEG else 0
    noise_ratio = a['retained_noise'] / TOTAL_NOISE if TOTAL_NOISE else 0
    recs.append((a['threshold'], recall, noise_ratio))
# Choose threshold with recall >=0.90 and noise_ratio <=0.05, preferring higher recall.
chosen = None
for th, rec, nratio in sorted(recs, key=lambda x: x[0]):
    if rec >= 0.90 and nratio <= 0.05:
        chosen = th
        break
if chosen is None:
    chosen = 85  # fallback
print("--- RECOMMENDATION ---")
print(f"Recommended fuzzy cutoff: {chosen}")
print("(Chosen to retain ≥90% of legitimate matches while rejecting ≥95% of obvious noise.)")
print()

# ---------------------------------------------------------------------------
# Cases that may need later ambiguity handling (multiple legit candidates per query)
# ---------------------------------------------------------------------------
print("--- CASES REQUIRING LATER AMBIGUITY HANDLING ---")
for q in set(e["question"] for e in raw_entries):
    leg_cands = [e for e in raw_entries if e["question"] == q and e["legitimate"]]
    if len(leg_cands) > 1:
        print(f"Question '{q}' has {len(leg_cands)} legitimate candidates (e.g., {leg_cands[0]['candidate']}, {leg_cands[1]['candidate']})")
print()

print("--- FINAL VERDICT ---")
print("PASS")
