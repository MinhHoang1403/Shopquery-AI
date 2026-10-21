"""PostgreSQL differential edge cases for COUNT sorting and untouched query clauses."""

import pytest
from sqlglot import exp, parse_one

from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.validator import ValidatedSql
from tests.auth_helpers import TEST_OWNER
from tests.join_domains import DOMAINS
from tests.test_join_domains_integration import (
    domain_workspace,  # noqa: F401
    golden_sql,
    oracle,
)
from tests.test_three_table_join_integration import scoped_validator

pytestmark = pytest.mark.integration
CASES = [
    ("tuition", 2, "fact_row_count", False, True, False),
    ("logistics", 3, "fact_row_count", True, False, True),
    ("sales", 2, "fact_value_count", True, False, False),
    ("staffing", 3, "fact_row_count", False, False, False),
    ("energy", 3, "fact_value_count", True, True, False),
    ("maintenance_holdout", 3, "fact_value_count", False, True, True),
]


@pytest.mark.parametrize(
    "domain_workspace,tables_count,alias,descending,quoted,reverse",
    [
        ((next(d for d in DOMAINS if d.name == name), 19), n, alias, desc, quote, reverse)
        for name, n, alias, desc, quote, reverse in CASES
    ],
    indirect=["domain_workspace"],
    ids=[c[0] for c in CASES],
)
def test_count_sort_edges_preserve_postgresql_semantics(
    domain_workspace,  # noqa: F811
    tables_count: int,
    alias: str,
    descending: bool,
    quoted: bool,
    reverse: bool,
) -> None:
    domain, _, _, dataset, _, context, facts = domain_workspace
    filtered = domain.name == "energy"
    expected = oracle(facts, tables_count, filtered)
    expected.sort(key=lambda row: ((-1 if descending else 1) * row[alias], row["entity_id"]))
    expected = expected[:2]
    sql = golden_sql(domain, dataset, tables_count, filtered)
    root = parse_one(sql, read="postgres")
    if not filtered:
        root.set(
            "where",
            exp.Where(
                this=exp.NEQ(
                    this=exp.column("event_id", table="f"), expression=exp.Literal.string("missing")
                )
            ),
        )
    if reverse:
        fact, join = root.args["from_"].this.copy(), root.args["joins"][0]
        root.args["from_"].set("this", join.this.copy())
        join.set("this", fact)
    projection = next(p for p in root.expressions if p.alias == alias)
    projection.set("alias", exp.to_identifier(alias if quoted else alias.upper(), quoted=quoted))
    order = exp.Ordered(this=projection.this.copy(), desc=descending, nulls_first=not descending)
    root.set("order", exp.Order(expressions=[order, exp.Ordered(this=exp.column("entity_id"))]))
    root.set("limit", exp.Limit(expression=exp.Literal.number(2)))
    raw = root.sql(dialect="postgres")
    canonical = root.copy()
    canonical.args["order"].expressions[0].set(
        "this", exp.Column(this=projection.args["alias"].copy())
    )
    executor = SqlExecutor(get_readonly_engine(), timeout_ms=5000, max_rows=200)
    assert executor.execute(ValidatedSql(raw, frozenset())) == expected
    assert (
        executor.execute(ValidatedSql(canonical.sql(dialect="postgres"), frozenset())) == expected
    )
    checked = scoped_validator(context).validate(raw)
    normalized = parse_one(checked.statement, read="postgres")
    for clause in ("expressions", "where", "group", "limit"):
        assert normalized.args.get(clause) == root.args.get(clause)
    assert normalized.args["order"] == canonical.args["order"]
    assert {j.args["on"].sql() for j in normalized.args["joins"]} == {
        j.args["on"].sql() for j in root.args["joins"]
    }
    assert scoped_validator(context).validate(checked.statement) == checked
    with RelationshipRepository(get_setup_engine(), TEST_OWNER).execution_guard(
        dataset.dataset_id,
        context.approved_joins,
        checked,
    ):
        assert executor.execute(checked) == expected
