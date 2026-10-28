"""Neutral summaries must not turn unverified aliases into business labels."""

from app.routing.hybrid_evidence import compose_answer
from app.text_to_sql.answer import compose_sql_answer
from tests.test_hybrid_answer_consistency import fixture


def test_missing_metadata_uses_neutral_summary_without_raw_alias():
    answer = compose_sql_answer([{"internal_metric_e0": "000012"}], ())
    assert "internal_metric_e0" not in answer
    assert "bảng dữ liệu" in answer


def test_verified_hybrid_summary_counts_the_same_decisions_including_unknowns():
    result, chunks, draft = fixture()
    draft.language = "vi"
    answer = compose_answer(result, chunks, draft)
    assert "**2 đối tượng đạt yêu cầu**" in answer
    assert "**2 đối tượng chưa đạt**" in answer
    assert "**1 đối tượng chưa đủ bằng chứng**" in answer
