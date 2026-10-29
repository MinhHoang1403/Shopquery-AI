"""Evaluation dispatch stays offline unless source/PG/budget gates are explicit."""

import json
import sys

import pytest

from scripts import evaluate_semantic_tasks as evaluation


def run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["evaluate", "--provider", "gemini", *args])
    monkeypatch.setattr(evaluation.subprocess, "check_output", lambda *a, **kw: "a" * 40)

    def forbidden(*args, **kwargs):
        pytest.fail("Provider must not be initialized before explicit acceptance gates")

    monkeypatch.setattr(evaluation, "build_generation_gateway", forbidden)
    return evaluation.main()


def test_default_evaluation_is_a_read_only_dry_run(monkeypatch, capsys):
    assert run(monkeypatch) == 0
    assert json.loads(capsys.readouterr().out)["dispatch"] is False


def test_live_evaluation_without_a_pg_receipt_cannot_dispatch(monkeypatch):
    with pytest.raises(SystemExit):
        run(monkeypatch, "--live", "--max-cases", "1")


@pytest.mark.parametrize("source,postgres", [("b" * 40, "PASS"), ("a" * 40, "FAIL")])
def test_stale_or_failed_postgres_receipt_never_dispatches(monkeypatch, tmp_path, source, postgres):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"source": source, "postgres": postgres}))
    with pytest.raises(SystemExit):
        run(monkeypatch, "--live", "--max-cases", "1", "--ci-receipt", str(receipt))


def test_synthetic_catalog_types_and_approved_relations_are_explicit():
    suite = json.loads(evaluation.FIXTURE.read_text())
    for name, descriptor in suite["contexts"].items():
        catalog = evaluation.catalog(name, descriptor)
        assert catalog.owner_user_id is not None and catalog.dataset_id == 1
        for edge in catalog.approved_joins:
            assert edge.source_column in catalog.table_columns[edge.source_table]
            assert edge.target_column in catalog.table_columns[edge.target_table]


def test_capture_records_the_synthetic_dto_before_failed_conversion_without_an_extra_call():
    from unittest.mock import Mock

    from app.core.errors import ModelResponseError
    from app.routing.router import QueryRouter
    from app.semantic.wire import TaskProposal
    from tests.semantic_fixtures import proposal

    data = proposal()
    data["sort"] = [{"field": "missing_alias", "direction": "asc", "nulls": "last"}]
    gateway = Mock(generate_structured=Mock(return_value=TaskProposal.model_validate(data)))
    capture = evaluation.ProposalCapture(gateway)
    with pytest.raises(ModelResponseError):
        QueryRouter(capture).route("Synthetic count and sum")
    assert capture.proposals == [data]
    gateway.generate_structured.assert_called_once()


def test_diagnostic_cannot_dispatch_without_a_recorded_failed_case(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "CACHE", tmp_path)
    receipt = tmp_path / "ci.json"
    receipt.write_text(json.dumps({"source": "a" * 40, "postgres": "PASS"}))
    with pytest.raises(SystemExit):
        run(
            monkeypatch,
            "--live",
            "--max-cases",
            "28",
            "--diagnostic-case",
            "p05",
            "--ci-receipt",
            str(receipt),
            "--env-file",
            str(tmp_path / "absent.env"),
        )
    assert not (tmp_path / "core_provider_budget.json").exists()
