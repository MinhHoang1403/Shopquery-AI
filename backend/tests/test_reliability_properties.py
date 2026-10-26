"""Bounded generated invariants; seeds are replayable and never call providers."""

import json
import random

import pytest
from pydantic import ValidationError

from app.core.errors import SqlValidationError
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.generation_contract import GenerationDecision
from app.text_to_sql.plan_binding import bind_approved_grain
from app.text_to_sql.query_plan import PlanExpression
from tests.test_plan_binding import setup_plan
from tests.test_planning_outcomes import wire


@pytest.mark.parametrize("seed", range(20))
def test_catalog_order_and_alias_renaming_cannot_change_issued_authority(seed):
    context, compiler, plan = setup_plan()
    tables = list(context.table_columns.items())
    random.Random(seed).shuffle(tables)
    from dataclasses import replace

    reordered = QueryCompiler(replace(context, table_columns=dict(tables)))
    assert compiler.references == reordered.references
    bound = bind_approved_grain(plan, compiler.references)
    result = compiler.compile(bound)
    renamed = bound.model_copy(
        update={
            "fields": [
                f.model_copy(update={"alias": f"metric_{seed}_{i}"})
                for i, f in enumerate(bound.fields)
            ]
        }
    )
    other = compiler.compile(renamed)
    assert other.parameters == result.parameters
    assert other.validated.tables == result.validated.tables
    assert other.validated.fact_table == result.validated.fact_table
    assert other.validated.relationship_ids == result.validated.relationship_ids
    assert [m.kind for m in other.validated.count_metrics] == [
        m.kind for m in result.validated.count_metrics
    ]


@pytest.mark.parametrize("clause", ["where", "having"])
@pytest.mark.parametrize(
    "value",
    [",having=[]}", ",limit=0,", "DROP TABLE t", "private_identifier", "e-1", "e0;SELECT 1"],
)
def test_malformed_predicates_are_rejected_at_wire_and_domain_boundaries(clause, value):
    with pytest.raises(ValidationError) as caught:
        GenerationDecision.model_validate(wire(**{clause: value}))
    assert caught.value.errors(include_input=False)[0]["type"] == "predicate_reference"


@pytest.mark.parametrize("seed", range(16))
def test_unknown_authority_never_turns_into_a_nearby_column(seed):
    _, compiler, plan = setup_plan()
    bad = plan.model_copy(
        update={"expressions": [PlanExpression(operation="sum", arguments=[f"t999.c{seed}"])]}
    )
    with pytest.raises(SqlValidationError) as caught:
        bind_approved_grain(bad, compiler.references)
    assert caught.value.error_context.validation_branch == "unknown_reference"
    assert "t999" not in caught.value.error_context.model_dump_json()


def test_captured_invalid_predicate_does_not_get_repaired_into_an_empty_filter():
    payload = wire(where=",having=[]}", having=",limit=0,")
    before = json.dumps(payload, sort_keys=True)
    with pytest.raises(ValidationError):
        GenerationDecision.model_validate(payload)
    assert json.dumps(payload, sort_keys=True) == before
