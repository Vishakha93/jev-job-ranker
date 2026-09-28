"""Thin wrapper around the TypeSafe SDK, plus an offline mock.

The mock implements the same surface the real SDK exposes
(Choice / Score / Noul questions, response.answers[...] with .choice,
.probabilities, .confidence, .score, .noul) using crude keyword heuristics.
It exists so the app runs with no API key and so tests are free and
deterministic. It is NOT a stand-in for Jev's judgment.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

PINNED_MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")  # pin: jev-latest can move under you

try:  # real SDK
    from typesafe_sdk import Choice, Noul, Score, TypeSafeClient  # type: ignore

    SDK_AVAILABLE = True
except ImportError:  # fall back to local definitions so the mock still works
    SDK_AVAILABLE = False

    @dataclass
    class Choice:  # type: ignore[no-redef]
        instructions: str
        criteria: dict[str, str]

    @dataclass
    class Score:  # type: ignore[no-redef]
        instructions: str
        criteria: list[str]

    @dataclass
    class Noul:  # type: ignore[no-redef]
        instructions: str


def make_client(api_key: str | None):
    """Return a real Jev client when possible, otherwise the mock."""
    if api_key and SDK_AVAILABLE:
        return TypeSafeClient(api_key=api_key, model=PINNED_MODEL)
    return MockJev()


# ---------------------------------------------------------------- mock ----

@dataclass
class _Answer:
    choice: str | None = None
    probabilities: Any = None
    confidence: float | None = None
    score: float | None = None
    noul: float | None = None


@dataclass
class _Response:
    answers: dict[str, _Answer]
    model: str = "mock"
    usage: dict = field(default_factory=dict)


def _flatten(state: Any) -> str:
    if isinstance(state, str):
        return state
    if isinstance(state, dict):
        return " ".join(_flatten(v) for v in state.values())
    if isinstance(state, (list, tuple)):
        return " ".join(_flatten(v) for v in state)
    return str(state)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", text.lower()))


class MockJev:
    """Keyword-overlap imitation of the Jev interface. Deterministic."""

    is_mock = True

    def system_one(self, state: Any, questions: dict[str, Any]) -> _Response:
        # Latest user message wins, mirroring the instruction we give real Jev.
        if isinstance(state, dict) and state.get("conversation"):
            convo = state["conversation"]
            focus = _flatten(convo[-1]) + " " + _flatten(convo)
        else:
            focus = _flatten(state)
        text = focus.lower()
        answers = {}
        for name, q in questions.items():
            if isinstance(q, Choice):
                answers[name] = self._choice(text, q)
            elif isinstance(q, Score):
                answers[name] = self._score(text, state, q)
            else:
                answers[name] = self._noul(text, state, q)
        return _Response(answers=answers)

    def _choice(self, text: str, q: Choice) -> _Answer:
        hits = {}
        for key, desc in q.criteria.items():
            cues = _words(key.replace("_", " ") + " " + desc) - {"a", "or", "the", "role", "roles", "any", "not"}
            hits[key] = sum(1 for c in cues if len(c) > 2 and c in text)
        fallback = next((k for k in q.criteria if k in ("not_stated", "no_preference", "other")), None)
        best = max(hits, key=hits.get)
        if hits[best] == 0 and fallback:
            best = fallback
        total = sum(hits.values()) or 1
        probs = {k: (v / total if total else 0) for k, v in hits.items()}
        conf = 0.9 if hits[best] >= 2 else 0.6 if hits[best] == 1 else 0.4
        return _Answer(choice=best, probabilities=probs, confidence=conf)

    def _score(self, text: str, state: Any, q: Score) -> _Answer:
        job = state.get("job", {}) if isinstance(state, dict) else {}
        job_words = _words(_flatten(job))
        want_words = _words(text)
        overlap = len(job_words & want_words)
        top = len(q.criteria) - 1
        score = min(top, overlap / 6 * top)
        return _Answer(score=round(score, 3), confidence=0.6)

    _WORKPLACE_TERMS = {
        "remote": r"remote|work from home|wfh",
        "hybrid": r"hybrid",
        "on-site": r"on-?site|on site|in[- ]office|in the office|in person",
    }
    _NEG = r"(?:no|not|don't|dont|never|avoid|without)\b(?:\W+\w+){0,3}?\W+"

    def _workplace(self, state: Any, instr: str) -> _Answer:
        wtype = next(k for k in self._WORKPLACE_TERMS if k in instr.split(":")[1])
        asks_ruled_out = "do not want" in instr
        msgs = state.get("conversation", []) if isinstance(state, dict) else [_flatten(state)]
        wants = ruled = False
        for m in msgs:  # later messages override earlier ones
            m = m.lower()
            term = self._WORKPLACE_TERMS[wtype]
            if re.search(self._NEG + f"(?:{term})", m):
                wants, ruled = False, True
            elif re.search(term, m):
                wants, ruled = True, False
            # "only remote" / "fully remote" excludes the other types
            for other, oterm in self._WORKPLACE_TERMS.items():
                if other != wtype and re.search(rf"(?:only|fully|strictly)\s+(?:{oterm})|(?:{oterm})\s+only", m):
                    wants, ruled = False, True
        return _Answer(noul=(0.9 if ruled else 0.05) if asks_ruled_out else (0.9 if wants else 0.1))

    def _noul(self, text: str, state: Any, q: Noul) -> _Answer:
        instr = q.instructions.lower()
        if instr.startswith("workplace arrangement:"):
            return self._workplace(state, instr)
        if "manag" in instr:
            return _Answer(noul=0.8 if "manage" in text and "not" not in text else 0.2)
        if "relocat" in instr:
            return _Answer(noul=0.8 if "relocat" in text or "move" in text else 0.2)
        if "explicitly said they do not want" in instr:
            job = state.get("job", {}) if isinstance(state, dict) else {}
            neg = re.findall(r"(?:no|not|don't|dont|avoid)\s+(?:want\s+to\s+|like\s+to\s+)?(\w+)", text)
            job_text = _flatten(job).lower()
            return _Answer(noul=0.85 if any(n in job_text for n in neg if len(n) > 3) else 0.1)
        return _Answer(noul=0.5)
