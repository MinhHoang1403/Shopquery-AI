"""Raw/normalized/guarded COUNT results must agree with independent PostgreSQL oracles."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from sqlglot import exp, parse_one

from app.core.errors import (
    ResourceConflictError,
    ResourceNotFoundError,
    SqlUnsupportedError,
    SqlValidationError,
)
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.dependencies import build_workspace_context
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import ValidatedSql
from tests.auth_helpers import TEST_OWNER
from tests.count_conformance import (
    POSITIVE_COUNTS,
    UNSAFE_COUNTS,
    output_names,
    selections,
    unsafe_query,
)
from tests.join_domains import DOMAINS
from tests.test_dataset_parser import parse
from tests.test_join_domains_integration import (
    domain_workspace,  # noqa: F401
    golden_sql,
    oracle,
)
from tests.test_three_table_join_integration import scoped_validator

pytestmark = pytest.mark.integration


def count_query(domain, dataset, tables_count, case):
    root = parse_one(
        golden_sql(domain, dataset, tables_count, domain.name == "energy"), read="postgres"
    )
    root.set(
        "expressions",
        root.expressions[:-2]
        + [
            parse_one(value, read="postgres")
            for value in selections(case, domain.keys[1], domain.measure)
        ],
    )
    ordering = [value.format(key=domain.keys[1], measure=domain.measure) for value in case.ordering]
    ordering.append("entity_id")
    root.set(
        "order", parse_one("SELECT 1 ORDER BY " + ",".join(ordering), read="postgres").args["order"]
    )
    limit = 2 if case.name in {"bare_rows", "quoted_rows", "multiple_metrics"} else 200
    root.set("limit", exp.Limit(expression=exp.Literal.number(limit)))
    return root.sql(dialect="postgres"), limit


def count_oracle(domain, facts, tables_count, case, limit):
    rows = oracle(facts, tables_count, domain.name == "energy")
    names = output_names(case, domain.measure)
    expected = []
    for row in rows:
        selected = {k: v for k, v in row.items() if k not in {"fact_row_count", "fact_value_count"}}
        for name, (_, _, kind) in zip(names, case.projections, strict=True):
            selected[name] = row["fact_value_count"] if kind == "values" else row["fact_row_count"]
        expected.append(selected)
    # Non-NULL repeated keys are fixture inputs, not a proof inferred by the application.
    for order in reversed(case.ordering):
        expression = order.format(key=domain.keys[1], measure=domain.measure).split()[0]
        if expression.startswith("COUNT("):
            kind = "values" if domain.measure in expression else "rows"
            field = next(
                name
                for name, (_, _, value) in zip(names, case.projections, strict=True)
                if value == kind or kind == "rows" and value == "key"
            )
        else:
            field = expression.strip('"').translate(
                str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
            )
        expected.sort(key=lambda row: row[field], reverse=" DESC" in order)
    return expected[:limit]


@pytest.mark.parametrize(
    "domain_workspace",
    [(domain, seed) for domain in DOMAINS for seed in (7, 19)],
    indirect=True,
    ids=[f"{d.name}-{s}" for d in DOMAINS for s in (7, 19)],
)
@pytest.mark.parametrize("tables_count", [1, 2, 3])
def test_count_conformance_postgresql(domain_workspace, tables_count):  # noqa: F811
    domain, _, repository, dataset, settings, _, facts = domain_workspace
    dataset = repository.add_table(dataset.dataset_id, parse("unrelated.csv", b"unused\nother\n"))
    reordered = tuple(replace(t, columns=t.columns[::-1]) for t in dataset.tables[::-1])
    context = build_workspace_context(settings, replace(dataset, tables=reordered), repository)
    assert len(context.table_columns) == 4 and len(context.approved_joins) == 2
    checked = scoped_validator(context)
    executor = SqlExecutor(get_readonly_engine(), timeout_ms=5000, max_rows=200)
    guard = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    for case in (POSITIVE_COUNTS[1], POSITIVE_COUNTS[0], *POSITIVE_COUNTS[2:]):
        if tables_count < case.min_tables:
            continue
        raw, limit = count_query(domain, dataset, tables_count, case)
        expected = count_oracle(domain, facts, tables_count, case, limit)
        assert executor.execute(ValidatedSql(raw, frozenset())) == expected, case.name
        result = checked.validate(raw)
        assert executor.execute(ValidatedSql(result.statement, frozenset())) == expected, case.name
        with guard.execution_guard(dataset.dataset_id, context.approved_joins, result):
            assert executor.execute(result) == expected, case.name
        assert [m.output_alias for m in result.count_metrics] == output_names(case, domain.measure)
        assert [m.kind.value for m in result.count_metrics] == [
            "non_null_value_count"
            if kind == "values" or kind == "key" and tables_count == 1
            else "row_count"
            for _, _, kind in case.projections
        ]
        for metric in result.count_metrics:
            original = parse_one(raw, read="postgres").expressions[metric.projection_index]
            original = original.this if isinstance(original, exp.Alias) else original
            normalized = parse_one(result.statement, read="postgres").expressions[
                metric.projection_index
            ]
            normalized = normalized.this if isinstance(normalized, exp.Alias) else normalized
            assert original == normalized == metric.source_aggregate
        assert checked.validate(result.statement) == result
        before, after = (
            parse_one(raw, read="postgres"),
            parse_one(result.statement, read="postgres"),
        )
        for clause in ("where", "group", "limit"):
            assert before.args.get(clause) == after.args.get(clause)
        assert sorted(j.args["on"].sql() for j in before.args.get("joins", [])) == sorted(
            j.args["on"].sql() for j in after.args.get("joins", [])
        )
    if tables_count >= 2:
        base = golden_sql(domain, dataset, tables_count)
        unauthorized = scoped_validator(replace(context, approved_joins=()))
        blocked_executor, blocked_gateway = Mock(), Mock()
        pipeline = TextToSqlPipeline(
            Mock(
                generate=Mock(
                    return_value=count_query(domain, dataset, tables_count, POSITIVE_COUNTS[0])[0]
                )
            ),
            unauthorized,
            blocked_executor,
            blocked_gateway,
        )
        with pytest.raises(SqlUnsupportedError):
            pipeline.run("COUNT without approved relationships")
        blocked_executor.execute.assert_not_called()
        blocked_gateway.generate_text.assert_not_called()
        for case in UNSAFE_COUNTS:
            sql = unsafe_query(
                base, case, key=domain.keys[1], measure=domain.measure, identifier="event_id"
            )
            rejected_executor, gateway, rejected_guard = Mock(), Mock(), Mock()
            pipeline = TextToSqlPipeline(
                Mock(generate=Mock(return_value=sql)),
                checked,
                rejected_executor,
                gateway,
                rejected_guard,
            )
            with pytest.raises(SqlValidationError) as caught:
                pipeline.run("Synthetic invalid COUNT")
            if case.reason:
                assert isinstance(caught.value, SqlUnsupportedError)
                assert caught.value.aggregate_reason == case.reason, case.name
            rejected_executor.execute.assert_not_called()
            gateway.generate_text.assert_not_called()
            rejected_guard.assert_not_called()


@pytest.mark.parametrize(
    "domain_workspace", [(d, 7) for d in DOMAINS], indirect=True, ids=[d.name for d in DOMAINS]
)
def test_count_provenance_never_authorizes_owner_workspace_or_revision(domain_workspace):  # noqa: F811
    from uuid import uuid4

    domain, _, repository, dataset, _, context, _ = domain_workspace
    sql, _ = count_query(domain, dataset, 3, POSITIVE_COUNTS[1])
    other = repository.create_workspace("Isolated COUNT foreign-binding test")
    stale = tuple(replace(r, revision="stale-synthetic") for r in context.approved_joins)
    try:
        guards = [
            lambda checked: RelationshipRepository(get_setup_engine(), TEST_OWNER).execution_guard(
                other.dataset_id, context.approved_joins, checked
            ),
            lambda checked: RelationshipRepository(get_setup_engine(), uuid4()).execution_guard(
                dataset.dataset_id, context.approved_joins, checked
            ),
            lambda checked: RelationshipRepository(get_setup_engine(), TEST_OWNER).execution_guard(
                dataset.dataset_id, stale, checked
            ),
        ]
        for build_guard in guards:
            executor, gateway = Mock(), Mock()
            pipeline = TextToSqlPipeline(
                Mock(generate=Mock(return_value=sql)),
                scoped_validator(context),
                executor,
                gateway,
                build_guard,
            )
            with pytest.raises((ResourceConflictError, ResourceNotFoundError)):
                pipeline.run("Synthetic count with invalid authorization")
            executor.execute.assert_not_called()
            gateway.generate_text.assert_not_called()
    finally:
        repository.delete(other.dataset_id, delete_conversations=True)
