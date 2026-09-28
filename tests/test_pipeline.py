"""Offline tests using the mock client. Run: python -m pytest -q  (or python tests/test_pipeline.py)"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ranker.jev_client import MockJev
from ranker.pipeline import DemoBudget, load_jobs, rank


def test_rank_returns_top_n_sorted():
    r = rank(MockJev(), load_jobs(), ["Senior backend engineer, remote, Java and Kafka"], top_n=25)
    assert len(r.ranked) == 25
    totals = [s.total for s in r.ranked]
    assert totals == sorted(totals, reverse=True)
    assert r.jev_calls == 1 + r.shortlist_size


def test_confident_remote_filter_applies():
    r = rank(MockJev(), load_jobs(), ["I want a fully remote backend role"])
    assert r.criteria.workplace["Remote"].wants > 0.5
    assert all(s.job["workplace_type"] == "Remote" for s in r.ranked)


def test_multi_workplace_excludes_only_ruled_out_type():
    r = rank(MockJev(), load_jobs(), ["backend role, remote or hybrid is fine, but no onsite"])
    types = {s.job["workplace_type"] for s in r.ranked}
    assert "On-site" not in types and types <= {"Remote", "Hybrid"}


def test_pdf_resume_extraction():
    import io
    from pypdf import PdfWriter
    from ranker.resume import ResumeError, resume_to_text
    buf = io.BytesIO(); w = PdfWriter(); w.add_blank_page(612, 792); w.write(buf)
    try:
        resume_to_text("blank.pdf", buf.getvalue())
        assert False, "blank PDF should raise"
    except ResumeError:
        pass
    assert resume_to_text("r.txt", b"Senior engineer, Java, Kafka") == "Senior engineer, Java, Kafka"


def test_later_message_changes_results():
    jobs = load_jobs()
    first = rank(MockJev(), jobs, ["remote frontend React role"])
    second = rank(MockJev(), jobs, ["remote frontend React role", "actually I want machine learning, pytorch ranking"])
    assert [s.job["id"] for s in first.ranked] != [s.job["id"] for s in second.ranked]


def test_demo_budget_caps():
    with tempfile.TemporaryDirectory() as d:
        b = DemoBudget(per_session=2, per_day=3, counter_file=Path(d) / "c.json")
        assert b.check(0) is None
        assert b.check(2) is not None          # session cap
        for _ in range(3):
            b.record()
        assert b.check(0) is not None          # daily cap


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
