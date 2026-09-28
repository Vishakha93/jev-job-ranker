"""Stage 2: Jev judges each shortlisted job.

Composite scoring: instead of asking "how good is this job for them?"
(several judgments hidden in one question), we ask narrow questions and
combine them with weights in code. Re-weighting is a code change, not a
re-prompt, so you can A/B it.

One call per job keeps each state small and focused (no context rot), and
calls run in parallel threads. Jev has no text output, so the "why" shown
in the UI is the typed breakdown itself.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .jev_client import Choice, Noul, Score

WEIGHTS = {"intent": 0.45, "skills": 0.30, "level": 0.25}
DEALBREAKER_PENALTY = 0.6
JOB_FIELDS = ["title", "company_size", "industry", "location", "workplace_type",
              "seniority", "min_years_experience", "skills", "description"]

INTENT_LEVELS = [
    "Clearly not what they asked for",
    "Loosely related",
    "Partially matches what they asked for",
    "Mostly matches what they asked for",
    "Matches nearly everything they asked for",
]
SKILL_LEVELS = [
    "Little overlap with the candidate's skills",
    "Some transferable overlap",
    "Solid overlap with core requirements",
    "Candidate's skills cover the requirements well",
]


@dataclass
class ScoredJob:
    job: dict
    total: float
    intent: float           # 0..1
    skills: float           # 0..1
    level_fit: float        # P(right level)
    level_verdict: str
    dealbreaker: float      # P(violates an explicit "don't want")
    intent_confidence: float


def _questions(has_resume: bool) -> dict:
    skills_source = "their resume" if has_resume else "the skills they mention in their messages"
    return {
        "intent": Score(
            instructions=(
                "How well this job matches what the candidate asked for in their messages. "
                "Where messages conflict, the most recent one takes precedence."
            ),
            criteria=INTENT_LEVELS,
        ),
        "skills": Score(
            instructions=f"How well the candidate's skills, based on {skills_source}, fit this job's requirements.",
            criteria=SKILL_LEVELS,
        ),
        "level": Choice(
            instructions="Whether this job's level suits the candidate's experience and stated target level.",
            criteria={
                "too_junior": "The job is below the candidate's level",
                "right_level": "The job is at about the candidate's level",
                "too_senior": "The job asks for clearly more experience than the candidate has",
                "not_enough_info": "There is not enough information to judge",
            },
        ),
        "dealbreaker": Noul(
            instructions=(
                "This job has a property the candidate explicitly said they do not want "
                "in their most recent relevant message."
            )
        ),
    }


def _score_one(client, job: dict, conversation: list[str], resume: str | None) -> ScoredJob:
    state = {"conversation": conversation, "job": {k: job[k] for k in JOB_FIELDS}}
    if resume:
        state["resume"] = resume
    a = client.system_one(state=state, questions=_questions(bool(resume))).answers

    intent = a["intent"].score / (len(INTENT_LEVELS) - 1)
    skills = a["skills"].score / (len(SKILL_LEVELS) - 1)
    probs = a["level"].probabilities or {}
    level_fit = float(probs.get("right_level", 1.0 if a["level"].choice == "right_level" else 0.5))
    dealbreaker = float(a["dealbreaker"].noul)

    total = WEIGHTS["intent"] * intent + WEIGHTS["skills"] * skills + WEIGHTS["level"] * level_fit
    total *= 1 - DEALBREAKER_PENALTY * dealbreaker
    return ScoredJob(
        job=job, total=round(total, 4), intent=intent, skills=skills,
        level_fit=level_fit, level_verdict=a["level"].choice, dealbreaker=dealbreaker,
        intent_confidence=float(a["intent"].confidence or 0),
    )


def score_jobs(client, jobs: list[dict], conversation: list[str], resume: str | None,
               max_workers: int = 8) -> list[ScoredJob]:
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(lambda j: _score_one(client, j, conversation, resume), jobs))
    return sorted(results, key=lambda s: s.total, reverse=True)
