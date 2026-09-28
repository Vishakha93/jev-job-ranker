"""Stage 1: cheap, deterministic retrieval in plain code.

Jev's docs are blunt that accuracy drops when state carries material the
question does not need, and Jev cannot look anything up. So we narrow the
pool in code first and only send a shortlist to Jev.

Filters are confidence-gated: a typed criterion only becomes a HARD filter
when Jev is confident about it. Below the gate it becomes a soft boost, so a
shaky read of the conversation can never silently hide good jobs.
"""
from __future__ import annotations

import re

from .criteria import Criteria

HARD_FILTER_CONFIDENCE = 0.75
RULED_OUT_THRESHOLD = 0.8  # Noul probability above which a workplace type is excluded
SENIORITY_ORDER = ["Junior", "Mid", "Senior", "Staff", "Principal"]
STOPWORDS = {"the", "and", "for", "with", "want", "looking", "role", "job", "work", "i'm", "that", "not"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#.]+", text.lower()) if len(t) > 2 and t not in STOPWORDS}


def _passes_hard_filters(job: dict, c: Criteria) -> bool:
    pref = c.workplace[job["workplace_type"]]
    if pref.ruled_out >= RULED_OUT_THRESHOLD:
        return False
    if c.seniority.value != "not_stated" and c.seniority.confidence >= HARD_FILTER_CONFIDENCE:
        target = SENIORITY_ORDER.index(c.seniority.value)
        # allow one level either side; Jev judges the fine fit later
        if abs(SENIORITY_ORDER.index(job["seniority"]) - target) > 1:
            return False
    # Location only hard-filters on-site/hybrid jobs, and only if the
    # candidate is not open to relocating.
    if (
        c.location.value != "not_stated"
        and c.location.confidence >= HARD_FILTER_CONFIDENCE
        and c.open_to_relocation < 0.5
        and job["workplace_type"] != "Remote"
        and job["location"] != c.location.value
    ):
        return False
    return True


def _soft_score(job: dict, c: Criteria, query_tokens: set[str]) -> float:
    job_tokens = _tokens(" ".join([job["title"], job["description"], " ".join(job["skills"])]))
    score = len(job_tokens & query_tokens)
    if c.role_family.value == job["role_family"]:
        score += 4 * c.role_family.confidence
    pref = c.workplace[job["workplace_type"]]
    score += 3 * pref.wants - 3 * pref.ruled_out
    if c.location.value == job["location"]:
        score += 2 * c.location.confidence
    if c.seniority.value == job["seniority"]:
        score += 2 * c.seniority.confidence
    return score


def retrieve(jobs: list[dict], c: Criteria, conversation: list[str], resume: str | None,
             limit: int = 40) -> list[dict]:
    query_tokens = _tokens(" ".join(conversation) + " " + (resume or ""))
    pool = [j for j in jobs if _passes_hard_filters(j, c)]
    if len(pool) < 10:  # filters too tight; fall back rather than show nothing
        pool = jobs
    pool.sort(key=lambda j: _soft_score(j, c, query_tokens), reverse=True)
    return pool[:limit]
