"""Jev Job Ranker: describe the job you want, get a ranked list.

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from ranker.jev_client import SDK_AVAILABLE, make_client
from ranker.pipeline import DemoBudget, load_jobs, rank
from ranker.resume import ResumeError, resume_to_text

st.set_page_config(page_title="Jev Job Ranker", page_icon="🧭", layout="wide")


def _secret(name: str, default=None):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except Exception:  # no secrets.toml present
        return os.environ.get(name, default)


DEMO_KEY = _secret("TYPESAFE_API_KEY")
budget = DemoBudget(
    per_session=int(_secret("DEMO_TURNS_PER_SESSION", 15)),
    per_day=int(_secret("DEMO_TURNS_PER_DAY", 300)),
    counter_file=Path(_secret("DEMO_COUNTER_FILE", ".demo_counter.json")),
)


@st.cache_data
def jobs():
    return load_jobs()


ss = st.session_state
ss.setdefault("conversation", [])   # the candidate's own messages; this IS the state Jev sees
ss.setdefault("result", None)
ss.setdefault("demo_turns", 0)

# ------------------------------------------------------------- sidebar ----
with st.sidebar:
    st.header("Setup")
    own_key = st.text_input("Your TypeSafe API key (optional)", type="password",
                            help="Used only for this session, never stored.")
    if own_key:
        api_key, mode = own_key, "your key"
    elif DEMO_KEY:
        api_key, mode = DEMO_KEY, "shared demo key"
    else:
        api_key, mode = None, "offline mock"
    if api_key and not SDK_AVAILABLE:
        st.error("typesafe-sdk is not installed, falling back to the mock. Run: pip install typesafe-sdk")
        mode = "offline mock"
    st.caption(f"Mode: **{mode}**")
    if mode == "offline mock":
        st.info("No key, so a keyword-matching mock stands in for Jev. Rankings are illustrative only.")

    st.subheader("Resume (optional)")
    uploaded = st.file_uploader("PDF, text or Markdown", type=["pdf", "txt", "md"])
    resume = ""
    if uploaded:
        try:
            resume = resume_to_text(uploaded.name, uploaded.getvalue())
            st.caption(f"Read {len(resume.split()):,} words from {uploaded.name}.")
        except ResumeError as e:
            st.error(str(e))
    resume = st.text_area("Or paste it", value=resume, height=160) or None

    top_n = st.slider("How many results", 5, 25, 25)
    if st.button("Start over"):
        ss.conversation, ss.result = [], None
        st.rerun()

client = make_client(api_key if mode != "offline mock" else None)

# ---------------------------------------------------------------- main ----
st.title("Jev Job Ranker")
st.write("Say what you want in a job, in your own words. Refine as you go; the list re-ranks every turn.")

chat_col, results_col = st.columns([2, 3], gap="large")

with chat_col:
    for msg in ss.conversation:
        st.chat_message("user").write(msg)

    prompt = st.chat_input("e.g. Senior backend role, remote, Java and Kafka, not managing people yet")
    if prompt:
        blocked = budget.check(ss.demo_turns) if mode == "shared demo key" else None
        if blocked:
            st.warning(blocked)
        else:
            ss.conversation.append(prompt)
            with st.spinner("Ranking..."):
                ss.result = rank(client, jobs(), ss.conversation, resume, top_n=top_n)
            if mode == "shared demo key":
                ss.demo_turns += 1
                budget.record()
            st.rerun()

    if ss.result:
        c = ss.result.criteria
        st.subheader("How Jev read you")
        st.caption("Typed answers with calibrated confidence. Only confident answers become hard filters.")
        rows = [
            ("Role", c.role_family.value, c.role_family.confidence),
            ("Level", c.seniority.value, c.seniority.confidence),
            ("Location", c.location.value, c.location.confidence),
        ]
        for label, value, conf in rows:
            st.write(f"{label}: **{value}**")
            st.progress(min(max(conf, 0.0), 1.0), text=f"confidence {conf:.2f}")
        st.write("Workplace (two yes/no questions per type):")
        for wtype, pref in c.workplace.items():
            status = "excluded" if pref.ruled_out >= 0.8 else "preferred" if pref.wants >= 0.5 else "neutral"
            st.write(f"{wtype}: wants {pref.wants:.0%}, ruled out {pref.ruled_out:.0%} ({status})")
        st.write(f"Open to relocating: {c.open_to_relocation:.0%}  |  Wants management: {c.wants_management:.0%}")

with results_col:
    r = ss.result
    if not r:
        st.info("Your ranked jobs will show up here.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Jev calls", r.jev_calls)
        m2.metric("Latency", f"{r.seconds:.2f}s")
        m3.metric("Est. cost", f"${r.est_cost_usd:.5f}")
        st.caption(f"{len(jobs())} jobs, {r.shortlist_size} shortlisted by code, top {len(r.ranked)} ranked by Jev. "
                   f"About {r.est_input_tokens:,} input tokens; output is free.")

        for i, s in enumerate(r.ranked, 1):
            j = s.job
            lo, hi = j["salary_range_k_usd"]
            with st.expander(f"{i}. {j['title']} at {j['company']}   ({s.total:.2f})", expanded=i <= 3):
                st.write(f"{j['location']}, {j['workplace_type']}  |  {j['industry']}, {j['company_size']}  |  ${lo}k to ${hi}k")
                st.write(j["description"])
                st.progress(s.intent, text=f"Matches what you asked for: {s.intent:.2f}")
                st.progress(s.skills, text=f"Skills fit: {s.skills:.2f}")
                st.progress(s.level_fit, text=f"Right level: {s.level_fit:.2f} ({s.level_verdict})")
                if s.dealbreaker > 0.5:
                    st.warning(f"Possible dealbreaker ({s.dealbreaker:.0%}): conflicts with something you said you don't want.")
