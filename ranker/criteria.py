"""Turn a free-form conversation into typed search criteria.

Jev does not generate text, so there is no "summary" step. The whole
conversation is the state, and we ask typed questions against it. Later
messages overriding earlier ones is spelled out in every instruction,
because Jev reads instructions literally.

This is the speculative fan-out pattern: every question is asked in one
call, whether or not the user has mentioned that topic yet. Extra questions
cost a few input tokens and almost no latency.
"""
from __future__ import annotations

from dataclasses import dataclass

from .jev_client import Choice, Noul

LATEST_WINS = (
    " Judge from the candidate's messages. If they changed their mind, "
    "the most recent message takes precedence over earlier ones."
)

ROLE_FAMILIES = {
    "backend": "Backend or server-side engineering",
    "frontend": "Frontend or web UI engineering",
    "fullstack": "Full stack engineering",
    "ml": "Machine learning engineering",
    "search": "Search, retrieval or relevance engineering",
    "data_eng": "Data engineering and pipelines",
    "data_sci": "Data science and analytics",
    "devops": "Platform, infrastructure, DevOps or SRE",
    "mobile": "iOS or Android mobile engineering",
    "security": "Security engineering",
    "pm": "Product management",
    "em": "Engineering management",
    "not_stated": "The candidate has not indicated a role type",
}
# Workplace is NOT a single Choice. People say "remote or hybrid, not onsite",
# which one-of-N cannot express. Instead: two Nouls per type, one for
# "specifically wants" and one for "has ruled out". Six cheap parallel questions.
WORKPLACE_TYPES = {
    "Remote": "remote work (fully work-from-home, no regular office attendance)",
    "Hybrid": "hybrid work (a mix of office days and home days)",
    "On-site": "on-site work (in the office every working day; also called onsite or in-office)",
}
SENIORITY = {
    "Junior": "Entry level, 0 to 2 years",
    "Mid": "Mid level, roughly 2 to 5 years",
    "Senior": "Senior, roughly 5 to 8 years",
    "Staff": "Staff, roughly 8 to 12 years",
    "Principal": "Principal, 12 or more years",
    "not_stated": "Level is not indicated by the messages or resume",
}
LOCATIONS = [
    "Plano, TX", "Dallas, TX", "Austin, TX", "Houston, TX", "San Francisco, CA",
    "San Jose, CA", "Los Angeles, CA", "Seattle, WA", "New York, NY", "Boston, MA",
    "Chicago, IL", "Denver, CO", "Atlanta, GA", "Raleigh, NC", "Toronto, ON",
]


@dataclass
class TypedAnswer:
    value: str
    confidence: float


@dataclass
class WorkplacePref:
    wants: float      # P(candidate specifically asked for this type)
    ruled_out: float  # P(candidate excluded this type)


@dataclass
class Criteria:
    role_family: TypedAnswer
    workplace: dict[str, WorkplacePref]
    seniority: TypedAnswer
    location: TypedAnswer
    open_to_relocation: float
    wants_management: float
    model: str = ""


def build_state(conversation: list[str], resume: str | None) -> dict:
    state: dict = {"conversation": conversation}
    if resume:
        state["resume"] = resume
    return state


def extract_criteria(client, conversation: list[str], resume: str | None) -> Criteria:
    location_options = {loc: f"Wants to work in or near {loc}" for loc in LOCATIONS}
    location_options["not_stated"] = "No specific city mentioned"

    questions = {
        "role_family": Choice(
            instructions="Which type of role the candidate is looking for." + LATEST_WINS,
            criteria=ROLE_FAMILIES,
        ),
        "seniority": Choice(
            instructions=(
                "The level the candidate is targeting. Use their stated target if given, "
                "otherwise infer from the resume." + LATEST_WINS
            ),
            criteria=SENIORITY,
        ),
        "location": Choice(
            instructions="The city the candidate wants to work in." + LATEST_WINS,
            criteria=location_options,
        ),
        "open_to_relocation": Noul(
            instructions="The candidate says they are willing to relocate." + LATEST_WINS
        ),
        "wants_management": Noul(
            instructions="The candidate wants a people management role." + LATEST_WINS
        ),
    }
    for wtype, desc in WORKPLACE_TYPES.items():
        questions[f"wants_{wtype}"] = Noul(
            instructions=f"Workplace arrangement: the candidate says they want or would prefer {desc}." + LATEST_WINS
        )
        questions[f"rules_out_{wtype}"] = Noul(
            instructions=(
                f"Workplace arrangement: the candidate says they do not want {desc}, or asks only for "
                "other arrangements in a way that excludes it." + LATEST_WINS
            )
        )

    r = client.system_one(state=build_state(conversation, resume), questions=questions)
    a = r.answers

    def typed(key: str) -> TypedAnswer:
        return TypedAnswer(a[key].choice, float(a[key].confidence or 0))

    return Criteria(
        role_family=typed("role_family"),
        workplace={
            w: WorkplacePref(float(a[f"wants_{w}"].noul), float(a[f"rules_out_{w}"].noul))
            for w in WORKPLACE_TYPES
        },
        seniority=typed("seniority"),
        location=typed("location"),
        open_to_relocation=float(a["open_to_relocation"].noul),
        wants_management=float(a["wants_management"].noul),
        model=getattr(r, "model", ""),
    )
