from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.routing.hybrid import HybridPipeline
from app.routing.hybrid_evidence import compose_answer, verified_classification
from tests.test_natural_policy import bound_fixture


def test_backend_decimal_classification_preserves_null_zero_aliases_and_citation():
    result, chunk, _, context = bound_fixture()
    draft = verified_classification(result, [chunk], context, "vi")
    assert [d.status for d in draft.decisions] == [
        "qualified",
        "not_qualified",
        "insufficient_evidence",
    ]
    assert draft.used_chunk_ids == [41]
    answer = compose_answer(result, [chunk], draft, context)
    assert "Đạt: E1." in answer and "Chưa đạt: E2." in answer
    assert "0.00" in answer and "NULL" in answer
    gateway = Mock()
    actual = HybridPipeline(
        Mock(run=Mock(return_value=result)),
        Mock(retrieve=Mock(return_value=[chunk])),
        gateway,
        context,
    ).run("Theo chính sách đơn vị nào đạt?")
    assert actual.sources[0].chunk_id == 41 and actual.answer == answer
    gateway.generate_structured.assert_not_called()


@pytest.mark.parametrize("mutation", ["owner", "dataset", "exception", "filtered", "top_n"])
def test_insufficient_or_unbound_policy_never_gets_an_automatic_verdict(mutation):
    from uuid import uuid4

    result, chunk, _, context = bound_fixture()
    if mutation == "owner":
        context = replace(context, owner_user_id=uuid4())
    elif mutation == "dataset":
        context = replace(context, dataset_id=99)
    elif mutation == "exception":
        chunk = replace(chunk, content=chunk.content + " Except waived units.")
    elif mutation == "filtered":
        result.sql = result.sql.replace("GROUP BY", "WHERE f.amount > 0 GROUP BY")
    else:
        result.sql += " LIMIT 1"
    assert verified_classification(result, [chunk], context, "vi") is None
