from dataclasses import replace

import pytest
from pydantic import ValidationError
from sqlglot import exp, parse_one

from app.core.errors import SqlValidationError
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.query_plan import PlanDecision, PlanField, PlanFilter, PlanSort, QueryPlan
from tests.test_three_table_join import PS, SC, TYPES
from tests.test_workspace_prompts import tuition_context


def field(compiler, table, name):
    return next(key for key, value in compiler.references.columns.items() if value == (table, name))


def source(compiler, table):
    return next(key for key, value in compiler.references.tables.items() if value == table)


def test_plan_round_trip_and_exact_parameter_binding():
    compiler = QueryCompiler(tuition_context())
    column = field(compiler, "tuition_fixture", "da_dong")
    plan = QueryPlan(
        source="t0",
        fields=[PlanField(reference=column, alias="total", aggregate="sum")],
        filters=[PlanFilter(reference=column, operator="gte", values=["9007199254740993"])],
    )
    assert QueryPlan.model_validate_json(plan.model_dump_json()) == plan
    result = compiler.compile(plan)
    assert result.parameters == {"value_0": 9007199254740993}
    assert "9007199254740993" not in result.validated.statement
    assert result.validated.tables == frozenset({"tuition_fixture"})


def test_count_values_and_rows_have_different_provenance():
    compiler = QueryCompiler(tuition_context())
    result = compiler.compile(
        QueryPlan(
            source="t0",
            fields=[
                PlanField(alias="rows", aggregate="row_count"),
                PlanField(
                    reference=field(compiler, "tuition_fixture", "da_dong"),
                    alias="values",
                    aggregate="value_count",
                ),
            ],
        )
    )
    assert [m.kind.value for m in result.validated.count_metrics] == [
        "row_count",
        "non_null_value_count",
    ]


def test_projection_wire_schema_and_internal_row_count_guard():
    schema = PlanField.model_json_schema()
    assert "aggregate" not in schema["properties"]
    assert schema["properties"]["reference"]["type"] == "string"
    assert schema["required"] == ["reference", "alias"]
    assert PlanField(alias="rows", aggregate="row_count").reference is None
    with pytest.raises(ValidationError, match="Row count does not take a value column"):
        PlanDecision.model_validate({
            "plan": {
                "source": "t2",
                "fields": [
                    {"reference": "t0.c0", "alias": "kho_id"},
                    {"reference": "t2.c0", "alias": "so_don", "aggregate": "row_count"},
                    {"reference": "t2.c2", "alias": "tong_phi", "aggregate": "sum"},
                ],
                "group_by": ["t0.c0"],
                "relationships": ["r1", "r0"],
            }
        })


def test_model_values_cannot_become_sql_instructions():
    compiler = QueryCompiler(tuition_context())
    key = field(compiler, "tuition_fixture", "ma_hoc_vien")
    payload = "x'); DROP TABLE users; --"
    result = compiler.compile(
        QueryPlan(
            source="t0",
            fields=[PlanField(reference=key, alias="id")],
            filters=[PlanFilter(reference=key, operator="eq", values=[payload])],
        )
    )
    assert result.parameters == {"value_0": payload}
    assert "DROP" not in result.validated.statement
    assert parse_one(result.validated.statement, read="postgres").find(exp.Delete) is None


@pytest.mark.parametrize(
    "change",
    [
        {"source": "uploaded_data.other_owner"},
        {"fields": [PlanField(reference="unknown", alias="x")]},
        {"relationships": ["unapproved"]},
        {
            "fields": [
                PlanField.model_construct(alias="x", aggregate="row_count", reference="t0.c0")
            ]
        },
        {
            "fields": [
                PlanField(alias="x", aggregate="row_count"),
                PlanField(alias="x", aggregate="row_count"),
            ]
        },
    ],
)
def test_unauthorized_or_invalid_references_are_rejected(change):
    base = QueryPlan(source="t0", fields=[PlanField(alias="rows", aggregate="row_count")])
    with pytest.raises(SqlValidationError):
        QueryCompiler(tuition_context()).compile(base.model_copy(update=change))


def test_three_table_plan_uses_only_backend_on_keys_and_fact_root():
    context = replace(
        tuition_context(),
        table_columns={t: set(c) for t, c in TYPES.items()},
        column_types=TYPES,
        allowed_schemas={t: "uploaded_data" for t in TYPES},
        approved_joins=(PS, SC),
    )
    compiler = QueryCompiler(context)
    identity = field(compiler, "courses", "course_id")
    result = compiler.compile(
        QueryPlan(
            source=source(compiler, "payments"),
            relationships=list(compiler.references.relationships),
            fields=[
                PlanField(reference=identity, alias="course"),
                PlanField(
                    reference=field(compiler, "payments", "amount"), alias="total", aggregate="sum"
                ),
                PlanField(alias="rows", aggregate="row_count"),
            ],
            group_by=[identity],
            sort=[PlanSort(field="total", direction="desc")],
            limit=5,
        )
    )
    assert result.validated.fact_table == "payments"
    assert set(result.validated.relationship_ids) == {PS.relationship_id, SC.relationship_id}
    assert len(list(parse_one(result.validated.statement, read="postgres").find_all(exp.Join))) == 2


def test_plan_contract_does_not_accept_raw_sql_or_unbounded_limit():
    with pytest.raises(ValidationError):
        QueryPlan(
            source="t0",
            fields=[PlanField(alias="x", aggregate="row_count")],
            sql="SELECT * FROM users",
        )
    with pytest.raises(ValidationError):
        QueryPlan(source="t0", fields=[PlanField(alias="x", aggregate="row_count")], limit=1001)
