"""Three bindings need one root grain, two approved keys and no fan-out."""

from unittest.mock import Mock

import pytest
from sqlglot import parse_one

from app.core.errors import SqlValidationError
from app.text_to_sql.join_policy import ApprovedJoin
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import SqlValidator

TYPES = {
    "payments": {
        "payment_id": "TEXT",
        "student_id": "TEXT",
        "course_id": "TEXT",
        "amount": "NUMERIC",
        "units": "BIGINT",
    },
    "students": {"student_id": "TEXT", "name": "TEXT", "course_id": "TEXT", "fee": "NUMERIC"},
    "courses": {"course_id": "TEXT", "title": "TEXT", "fee": "NUMERIC"},
}
PS = ApprovedJoin("ps", "payments", "student_id", "students", "student_id", "r1")
SC = ApprovedJoin("sc", "students", "course_id", "courses", "course_id", "r2")
PC = ApprovedJoin("pc", "payments", "course_id", "courses", "course_id", "r3")
CHAIN_ORDERS = [
    "FROM uploaded_data.payments p INNER JOIN uploaded_data.students s "
    "ON p.student_id=s.student_id "
    "INNER JOIN uploaded_data.courses c ON s.course_id=c.course_id",
    "FROM uploaded_data.students s INNER JOIN uploaded_data.payments p "
    "ON p.student_id=s.student_id "
    "INNER JOIN uploaded_data.courses c ON s.course_id=c.course_id",
    "FROM uploaded_data.students s INNER JOIN uploaded_data.courses c ON s.course_id=c.course_id "
    "INNER JOIN uploaded_data.payments p ON p.student_id=s.student_id",
    "FROM uploaded_data.courses c INNER JOIN uploaded_data.students s ON s.course_id=c.course_id "
    "INNER JOIN uploaded_data.payments p ON p.student_id=s.student_id",
]


def validator(relations=(PS, SC), *, limit=3, enabled=True):
    return SqlValidator(
        {name: set(cols) for name, cols in TYPES.items()},
        {name: "uploaded_data" for name in TYPES},
        max_tables=limit,
        approved_joins=relations,
        column_types=TYPES,
        join_v1_enabled=enabled,
    )


@pytest.mark.parametrize("bindings", CHAIN_ORDERS)
@pytest.mark.parametrize("count", ["COUNT(*)", "COUNT(p.student_id)"])
def test_chain_normalizes_order_and_fact_key_count_without_changing_grain(bindings, count):
    result = validator().validate(
        f"SELECT c.course_id,c.title,SUM(p.amount) AS total,AVG(p.amount) AS average, "
        f"{count} AS fact_row_count,COUNT(p.amount) AS fact_value_count "
        f"{bindings} GROUP BY c.course_id,c.title ORDER BY c.course_id"
    )
    assert result.fact_table == "payments"
    assert result.relationship_id is None
    assert result.relationship_ids == ("ps", "sc")
    assert result.tables == frozenset(TYPES)
    root = parse_one(result.statement, read="postgres")
    assert root.args["from_"].this.name == "payments"
    assert [join.this.name for join in root.args["joins"]] == ["students", "courses"]
    assert "COUNT(*) AS fact_row_count" in result.statement
    assert validator().validate(result.statement) == result


@pytest.mark.parametrize("reverse", [False, True])
def test_star_uses_payments_as_fact_independent_of_from_position(reverse):
    bindings = (
        "FROM uploaded_data.students s INNER JOIN uploaded_data.payments p "
        "ON p.student_id=s.student_id"
        if reverse
        else "FROM uploaded_data.payments p INNER JOIN uploaded_data.students s "
        "ON p.student_id=s.student_id"
    )
    result = validator((PS, PC)).validate(
        "SELECT s.name,c.title,SUM(p.amount) AS total,COUNT(p.course_id) AS fact_row_count "
        + bindings
        + " INNER JOIN uploaded_data.courses c ON p.course_id=c.course_id "
        "GROUP BY s.student_id,s.name,c.course_id,c.title"
    )
    assert result.fact_table == "payments"
    assert set(result.relationship_ids) == {"ps", "pc"}


@pytest.mark.parametrize(
    "projection",
    [
        "SUM(s.fee)",
        "AVG(c.fee)",
        "COUNT(s.course_id) AS fact_row_count",
        "COUNT(p.payment_id) AS fact_row_count",
        "COUNT(DISTINCT p.student_id) AS fact_value_count",
        "SUM(p.amount * p.units)",
        "SUM(p.amount) FILTER(WHERE p.amount>0)",
        "COALESCE(SUM(p.amount),0)",
        "COUNT(*) AS fact_value_count",
        "*",
    ],
)
def test_dimension_or_unsafe_aggregate_never_reaches_guard_executor_or_answer(projection):
    executor, gateway, guard = Mock(), Mock(), Mock()
    pipeline = TextToSqlPipeline(
        Mock(generate=Mock(return_value=f"SELECT {projection} {CHAIN_ORDERS[0]}")),
        validator(),
        executor,
        gateway,
        execution_guard=guard,
    )
    with pytest.raises(SqlValidationError):
        pipeline.run("Synthetic negative")
    guard.assert_not_called()
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        lambda q: q.replace("p.student_id=s.student_id", "p.payment_id=s.student_id"),
        lambda q: q.replace("s.course_id=c.course_id", "s.student_id=c.course_id"),
        lambda q: q.replace("s.course_id=c.course_id", "s.course_id=c.course_id OR 1=1"),
        lambda q: q.replace("s.course_id=c.course_id", "s.course_id=c.course_id AND p.amount>0"),
        lambda q: q.replace("INNER JOIN", "LEFT JOIN", 1),
        lambda q: q.replace("INNER JOIN", "CROSS JOIN", 1),
        lambda q: q.replace("uploaded_data.courses", "public.courses"),
        lambda q: q.replace("courses c ON", "courses s ON"),
        lambda q: q + " FOR UPDATE",
        lambda q: q + "; DELETE FROM users",
        lambda q: q.replace("SELECT SUM(p.amount)", "SELECT SUM(x.amount)"),
        lambda q: q + " INNER JOIN uploaded_data.payments p2 ON p2.student_id=s.student_id",
    ],
)
def test_three_table_shape_keys_aliases_and_select_only_are_not_repaired(change):
    with pytest.raises(SqlValidationError):
        validator().validate(change("SELECT SUM(p.amount) " + CHAIN_ORDERS[0]))


@pytest.mark.parametrize(
    "relations",
    [
        (),
        (PS,),
        (PS, SC, PC),
        (PS, SC, SC),
        (PS, ApprovedJoin("back", "courses", "course_id", "students", "course_id", "r")),
    ],
)
def test_missing_ambiguous_and_two_fact_graphs_are_rejected(relations):
    with pytest.raises(SqlValidationError):
        validator(relations).validate("SELECT SUM(p.amount) " + CHAIN_ORDERS[0])


def test_future_alias_in_on_cannot_be_fixed_by_reordering():
    sql = (
        "SELECT SUM(p.amount) FROM uploaded_data.payments p "
        "INNER JOIN uploaded_data.courses c ON s.course_id=c.course_id "
        "INNER JOIN uploaded_data.students s ON p.student_id=s.student_id"
    )
    with pytest.raises(SqlValidationError):
        validator().validate(sql)


@pytest.mark.parametrize("limit,enabled", [(2, True), (3, False)])
def test_old_explicit_two_table_limit_and_feature_off_remain_closed(limit, enabled):
    with pytest.raises(SqlValidationError):
        validator(limit=limit, enabled=enabled).validate("SELECT SUM(p.amount) " + CHAIN_ORDERS[0])
