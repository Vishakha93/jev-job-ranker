"""End-to-end: conversation (+ optional resume) -> top N jobs.

Each chat turn re-runs the whole pipeline. That is affordable only because
Jev is cheap and fast: one criteria call plus one call per shortlisted job.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .criteria import Criteria, extract_criteria
from .retrieval import retrieve
from .scoring import ScoredJob, score_jobs

PRICE_PER_MTOK_INPUT = 0.042  # USD, output is free. Check typesafe.ai for current pricing.
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.json"


def load_jobs(path: Path = DATA_PATH) -> list[dict]:
    return json.loads(Path(path).read_text())


@dataclass
class RankResult:
    criteria: Criteria
    ranked: list[ScoredJob]
    shortlist_size: int
    jev_calls: int
    est_input_tokens: int
    est_cost_usd: float
    seconds: float


def _approx_tokens(obj) -> int:
    return len(json.dumps(obj)) // 4  # rough; the API response reports real usage


def rank(client, jobs: list[dict], conversation: list[str], resume: str | None = None,
         top_n: int = 25, shortlist: int = 40) -> RankResult:
    t0 = time.perf_counter()
    criteria = extract_criteria(client, conversation, resume)
    candidates = retrieve(jobs, criteria, conversation, resume, limit=shortlist)
    scored = score_jobs(client, candidates, conversation, resume)

    base = _approx_tokens({"c": conversation, "r": resume or ""})
    # ~350 tokens of question text per call, plus each job's fields
    tokens = (base + 600) + sum(base + 350 + _approx_tokens(j) for j in candidates)
    return RankResult(
        criteria=criteria,
        ranked=scored[:top_n],
        shortlist_size=len(candidates),
        jev_calls=1 + len(candidates),
        est_input_tokens=tokens,
        est_cost_usd=tokens / 1_000_000 * PRICE_PER_MTOK_INPUT,
        seconds=time.perf_counter() - t0,
    )


class DemoBudget:
    """Guardrails for the hosted demo that runs on the owner's key.

    Two caps: turns per browser session, and turns per day across everyone.
    The daily counter lives in a local file, which is good enough for a
    single-instance free-tier deploy. The real backstop is a spend limit on
    the TypeSafe account itself.
    """

    def __init__(self, per_session: int, per_day: int, counter_file: Path):
        self.per_session = per_session
        self.per_day = per_day
        self.counter_file = Path(counter_file)

    def _read(self) -> dict:
        try:
            data = json.loads(self.counter_file.read_text())
            return data if data.get("day") == date.today().isoformat() else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def check(self, session_turns: int) -> str | None:
        """Return a reason string if blocked, else None."""
        if session_turns >= self.per_session:
            return f"This demo session has used its {self.per_session} searches. Add your own key in the sidebar to keep going."
        if self._read().get("count", 0) >= self.per_day:
            return "The shared demo hit its daily limit. Add your own key in the sidebar, or come back tomorrow."
        return None

    def record(self) -> None:
        data = self._read()
        data = {"day": date.today().isoformat(), "count": data.get("count", 0) + 1}
        self.counter_file.write_text(json.dumps(data))
