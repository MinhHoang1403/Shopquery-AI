import pytest

from app.database.session import get_readonly_engine
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.query_plan import PlanField, PlanFilter, PlanSort, QueryPlan
from tests.join_domains import DOMAINS
from tests.test_join_domains_integration import domain_workspace, oracle  # noqa: F401
from tests.test_query_compiler import field, source

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("domain_workspace", [(DOMAINS[0], 19)], indirect=True)
@pytest.mark.parametrize("tables_count", [1, 2, 3])
@pytest.mark.parametrize("filtered", [False, True])
def test_bound_plan_matches_independent_postgres_oracle(
    domain_workspace,  # noqa: F811
    tables_count,
    filtered,
):
    domain, _, _, dataset, _, context, facts = domain_workspace
    names = {table.display_name: table.physical_table_name for table in dataset.tables}
    outer, inner, fact = [names[name] for name in domain.labels]
    used = (
        {fact}
        | ({inner} if tables_count >= 2 else set())
        | ({outer} if tables_count == 3 else set())
    )
    compiler = QueryCompiler(context)
    identity_table = outer if tables_count == 3 else inner if tables_count == 2 else fact
    identity = field(compiler, identity_table, domain.keys[0 if tables_count == 3 else 1])
    fields = [PlanField(reference=identity, alias="entity_id")]
    grouping = [identity]
    if tables_count >= 2:
        label = field(compiler, identity_table, domain.names[0 if tables_count == 3 else 1])
        fields.append(PlanField(reference=label, alias="entity_name"))
        grouping.append(label)
    measure = field(compiler, fact, domain.measure)
    fields.extend(
        [
            PlanField(reference=measure, alias="total", aggregate="sum"),
            PlanField(reference=measure, alias="average", aggregate="avg"),
            PlanField(alias="fact_row_count", aggregate="row_count"),
            PlanField(reference=measure, alias="fact_value_count", aggregate="value_count"),
        ]
    )
    filters = []
    if filtered:
        timestamp = field(compiler, fact, "recorded_at")
        filters = [
            PlanFilter(reference=timestamp, operator="gte", values=["2025-09-01T00:00:00+07:00"]),
            PlanFilter(reference=timestamp, operator="lt", values=["2025-10-01T00:00:00+07:00"]),
        ]
    plan = QueryPlan(
        source=source(compiler, fact),
        fields=fields,
        filters=filters,
        group_by=grouping,
        sort=[PlanSort(field="entity_id")],
        relationships=[
            key
            for key, edge in compiler.references.relationships.items()
            if edge.source_table in used and edge.target_table in used
        ],
    )
    compiled = compiler.compile(plan)
    actual = SqlExecutor(get_readonly_engine(), 3000, 100).execute(
        compiled.validated, compiled.parameters
    )
    assert actual == oracle(facts, tables_count, filtered)
