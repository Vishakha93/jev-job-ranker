# Jev Job Ranker

Describe the job you want in plain English, optionally add your resume, and get a ranked list of matching jobs. Keep chatting to refine it; the list re-ranks every turn.

It is a learning project for [Jev](https://typesafe.ai), TypeSafe AI's System One model. Jev does not generate text. It takes state plus typed questions and returns typed answers (Choice, Score, Noul) with calibrated confidence. This repo is a small, readable example of using that primitive for ranking.

All job data is synthetic (`data/generate_jobs.py`). No real postings, no scraping.

## Try it

```bash
pip install -r requirements.txt
streamlit run app.py
```

No key? It runs in **offline mock mode**: a keyword-matching stand-in with the same interface as Jev. Useful for exploring the UI and running tests, but its rankings say nothing about Jev's quality.

To use real Jev, paste a key in the sidebar (from console.typesafe.ai) or set `TYPESAFE_API_KEY`.

## How it works

Every chat turn runs three stages:

| Stage | Who does it | What happens |
|---|---|---|
| 1. Read the candidate | Jev, 1 call | Your messages (and resume) are the state. Typed questions extract role type, level, city, openness to relocation, interest in management, and for each workplace type (Remote, Hybrid, On-site) whether you want it and whether you ruled it out. All asked in one call. |
| 2. Shortlist | Plain code | Filters and keyword scoring over 1,000 jobs down to 40. A criterion only becomes a hard filter if Jev's confidence is at least 0.75; below that it is a soft boost. |
| 3. Judge | Jev, 1 call per job, parallel | Narrow questions per job: intent match (Score), skills fit (Score), level fit (Choice), dealbreaker (Noul). Combined with weights in `ranker/scoring.py`. |

Design choices, and why:

- **No summary step.** Jev cannot write text, so the conversation itself is the state. Every instruction says the most recent message wins, because Jev reads instructions literally.
- **Retrieve, then judge.** Jev knows only what is in the state, and accuracy drops as state fills with irrelevant material. Code narrows first; Jev judges a small, focused state.
- **Composite scoring.** Several narrow judgments beat one "how good is this job?" question. Reweighting is a code change you can A/B.
- **Workplace as yes/no per type, not one Choice.** People say "remote or hybrid, not onsite." A one-of-N question cannot hold that; six Nouls can.
- **Resumes.** PDF, .txt or .md. PDFs are converted to text (Jev is text only); scanned image PDFs are rejected with a clear message. Capped at 20k characters because the resume rides along on every call.
- **Confidence gating.** Uncertain reads of what you want never silently hide jobs.
- **Arithmetic stays in code.** Salary and experience numbers are not compared by Jev.
- **Pinned model.** `jev-1.13.0` by default (`JEV_MODEL` to change) so thresholds do not shift under you.

## Cost

Roughly 41 calls and about 20k input tokens per turn, which is under $0.001 at $0.042 per million input tokens (output is free). The app shows an estimate every turn. Check typesafe.ai for current pricing.

## Hosting a public demo

1. Deploy to Streamlit Community Cloud (or similar) and add `TYPESAFE_API_KEY` in its secrets settings.
2. Set `DEMO_TURNS_PER_SESSION` and `DEMO_TURNS_PER_DAY` to taste.
3. Set a hard spend limit on the TypeSafe account. The in-app caps are a courtesy; the account limit is the real backstop.

Visitors who paste their own key bypass the demo caps.

## Tests

```bash
python -m pytest -q
```

Tests run against the mock, so they are free and deterministic.

## Known limits

- The mock is crude, especially on seniority. Judge ranking quality with real Jev only.
- Jev can return the wrong valid answer. Consider a small labeled set of queries to evaluate against before trusting weights.
- User messages go straight into the state. Text written to steer a classification can move it; fine for a personal tool, worth thinking about if you build on this.
