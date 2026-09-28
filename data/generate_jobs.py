"""Generate a synthetic, reproducible job dataset.

Run:  python data/generate_jobs.py --count 1000
Writes data/jobs.json. Everything here is invented; no real postings are used.
"""
import argparse
import json
import random
from pathlib import Path

ROLE_FAMILIES = {
    "backend": ("Backend Engineer", ["Java", "Go", "Kafka", "microservices", "SQL", "gRPC"]),
    "frontend": ("Frontend Engineer", ["React", "TypeScript", "CSS", "accessibility", "Next.js"]),
    "fullstack": ("Full Stack Engineer", ["React", "Node.js", "Python", "PostgreSQL", "REST APIs"]),
    "ml": ("Machine Learning Engineer", ["PyTorch", "ranking", "embeddings", "MLOps", "feature stores"]),
    "search": ("Search Engineer", ["information retrieval", "Elasticsearch", "ranking", "query understanding", "Java"]),
    "data_eng": ("Data Engineer", ["Spark", "Airflow", "dbt", "ETL", "Snowflake"]),
    "data_sci": ("Data Scientist", ["statistics", "A/B testing", "Python", "SQL", "causal inference"]),
    "devops": ("Platform Engineer", ["Kubernetes", "Terraform", "AWS", "CI/CD", "observability"]),
    "mobile": ("Mobile Engineer", ["Swift", "Kotlin", "iOS", "Android", "React Native"]),
    "security": ("Security Engineer", ["threat modeling", "IAM", "cryptography", "AppSec", "incident response"]),
    "pm": ("Product Manager", ["roadmapping", "user research", "analytics", "stakeholder management"]),
    "em": ("Engineering Manager", ["people management", "hiring", "planning", "mentorship", "delivery"]),
}

SENIORITY = {
    "Junior": (0, (70, 110)),
    "Mid": (2, (100, 150)),
    "Senior": (5, (145, 210)),
    "Staff": (8, (200, 280)),
    "Principal": (12, (260, 360)),
}
# Managers and PMs rarely have "Junior" titles.
NO_JUNIOR = {"pm", "em"}

LOCATIONS = [
    "Plano, TX", "Dallas, TX", "Austin, TX", "Houston, TX", "San Francisco, CA",
    "San Jose, CA", "Los Angeles, CA", "Seattle, WA", "New York, NY", "Boston, MA",
    "Chicago, IL", "Denver, CO", "Atlanta, GA", "Raleigh, NC", "Toronto, ON",
]
WORKPLACE = ["Remote", "Hybrid", "On-site"]
COMPANY_SIZE = ["Startup (<50)", "Growth (50-500)", "Mid-size (500-5k)", "Enterprise (5k+)"]
INDUSTRIES = ["fintech", "healthcare", "e-commerce", "developer tools", "climate",
              "gaming", "logistics", "edtech", "cybersecurity", "media"]
COMPANY_PREFIX = ["North", "Blue", "Iron", "Bright", "Clear", "Quiet", "Swift", "Tall", "Red", "Open"]
COMPANY_SUFFIX = ["wind", "harbor", "leaf", "stack", "path", "forge", "field", "loop", "peak", "grid"]

DESCRIPTION_TEMPLATES = [
    "Join our {industry} team to build {focus}. You will work mostly with {skills}.",
    "We are a {size_word} {industry} company looking for someone to own {focus}. Day to day: {skills}.",
    "Help us scale {focus} for millions of users in {industry}. Stack includes {skills}.",
]
FOCUS = {
    "backend": "high-throughput services", "frontend": "our customer-facing web app",
    "fullstack": "end-to-end product features", "ml": "ranking and recommendation models",
    "search": "search relevance and retrieval", "data_eng": "reliable data pipelines",
    "data_sci": "experimentation and insights", "devops": "our cloud platform",
    "mobile": "our iOS and Android apps", "security": "product and infrastructure security",
    "pm": "the product roadmap for a core surface", "em": "a team of 6 to 10 engineers",
}


def make_job(i: int, rng: random.Random) -> dict:
    family = rng.choice(list(ROLE_FAMILIES))
    base_title, skill_pool = ROLE_FAMILIES[family]
    levels = [s for s in SENIORITY if not (family in NO_JUNIOR and s == "Junior")]
    seniority = rng.choice(levels)
    min_years, (lo, hi) = SENIORITY[seniority]
    skills = rng.sample(skill_pool, k=rng.randint(2, min(4, len(skill_pool))))
    workplace = rng.choice(WORKPLACE)
    location = "Remote (US)" if workplace == "Remote" and rng.random() < 0.5 else rng.choice(LOCATIONS)
    size = rng.choice(COMPANY_SIZE)
    industry = rng.choice(INDUSTRIES)
    salary_low = rng.randint(lo, hi - 20)
    description = rng.choice(DESCRIPTION_TEMPLATES).format(
        industry=industry,
        focus=FOCUS[family],
        skills=", ".join(skills),
        size_word=size.split(" ")[0].lower(),
    )
    return {
        "id": f"job_{i:04d}",
        "title": f"{seniority} {base_title}",
        "role_family": family,
        "company": rng.choice(COMPANY_PREFIX) + rng.choice(COMPANY_SUFFIX),
        "industry": industry,
        "company_size": size,
        "location": location,
        "workplace_type": workplace,
        "seniority": seniority,
        "min_years_experience": min_years,
        "salary_range_k_usd": [salary_low, salary_low + rng.randint(20, 60)],
        "skills": skills,
        "description": description,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default=str(Path(__file__).parent / "jobs.json"))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    jobs = [make_job(i + 1, rng) for i in range(args.count)]
    Path(args.out).write_text(json.dumps(jobs, indent=2))
    print(f"Wrote {len(jobs)} jobs to {args.out}")


if __name__ == "__main__":
    main()
