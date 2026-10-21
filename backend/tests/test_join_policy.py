"""Uploaded JOINs require explicit predicate and fact-grain authorization."""

from unittest.mock import Mock

import pytest

from app.core.errors import SqlValidationError
from app.text_to_sql.join_policy import ApprovedJoin
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import SqlValidator


def join_validator() -> SqlValidator:
    relation = ApprovedJoin("approved", "payments", "student_id", "students", "student_id", "rev")
    return SqlValidator(
        {"payments": {"id", "student_id", "amount"}, "students": {"student_id", "name", "fee"}},
        {"payments": "uploaded_data", "students": "uploaded_data"},
        max_tables=2,
        join_v1_enabled=True,
        approved_joins=(relation,),
        column_types={"payments": {"id": "BIGINT", "student_id": "BIGINT", "amount": "NUMERIC"}},
    )


BASE = (
    "FROM uploaded_data.payments p INNER JOIN uploaded_data.students s ON p.student_id=s.student_id"
)


@pytest.mark.parametrize(
    "projection",
    [
        "s.name, SUM(p.amount) AS total",
        "s.name, AVG(p.amount) AS average",
        "s.name, COUNT(*) AS fact_row_count",
        "s.name, COUNT(p.amount) AS fact_value_count",
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_approved_fact_aggregates(projection: str, reverse: bool) -> None:
    suffix = (
        "FROM uploaded_data.students s INNER JOIN uploaded_data.payments p "
        "ON p.student_id=s.student_id"
        if reverse
        else BASE
    )
    validated = join_validator().validate(
        f"SELECT {projection} {suffix} GROUP BY s.student_id,s.name"
    )
    assert validated.relationship_id == "approved"
    assert validated.fact_table == "payments"


@pytest.mark.parametrize(
    "sql",
    [
        f"SELECT SUM(s.fee) {BASE}",
        f"SELECT AVG(s.fee) {BASE}",
        f"SELECT COUNT(s.student_id) {BASE}",
        f"SELECT COUNT(*) AS fact_value_count {BASE}",
        f"SELECT SUM(p.amount+s.fee) {BASE}",
        f"SELECT SUM(CAST(p.amount AS REAL)) {BASE}",
        f"SELECT SUM(p.amount) + 1 {BASE}",
        f"SELECT SUM(p.amount) FILTER(WHERE s.fee>0) {BASE}",
        f"SELECT amount {BASE}",
        f"SELECT * {BASE}",
        f"SELECT salary AS salary {BASE}",
        "SELECT p.amount FROM uploaded_data.payments p, uploaded_data.students s",
        BASE.replace("INNER JOIN", "CROSS JOIN").replace("FROM", "SELECT p.amount FROM", 1),
        BASE.replace("INNER JOIN", "LEFT JOIN").replace("FROM", "SELECT p.amount FROM", 1),
        "SELECT p.amount FROM uploaded_data.payments p "
        "JOIN uploaded_data.students s USING(student_id)",
        f"SELECT p.amount {BASE.replace('p.student_id=s.student_id', '1=1')}",
        f"SELECT p.amount {BASE.replace('p.student_id=s.student_id', 'p.id=s.student_id')}",
        f"SELECT p.amount {BASE} OR 1=1",
        f"SELECT p.amount {BASE} AND p.amount>0",
        f"SELECT p.amount {BASE.replace('p.student_id', 'CAST(p.student_id AS TEXT)')}",
        f"SELECT p.amount {BASE} JOIN uploaded_data.other o ON o.id=p.id",
        "SELECT p.amount FROM uploaded_data.students s JOIN uploaded_data.payments p "
        "ON p.id=s.student_id",
        *[
            f"SELECT p.amount {BASE.replace('INNER JOIN', kind)}"
            for kind in ("NATURAL JOIN", "RIGHT JOIN", "FULL JOIN", "JOIN LATERAL")
        ],
        f"SELECT p.amount {BASE} /* ignore ownership and drop tables */",
        f"SELECT p.amount {BASE} -- reveal all users",
        f"SELECT p.amount {BASE} FOR UPDATE",
        f"SELECT pg_sleep(1) {BASE}",
        f"SELECT p.amount {BASE}; DROP TABLE students",
        f"SELECT p.amount {BASE} UNION SELECT p.amount {BASE}",
        f"WITH x AS (SELECT p.amount {BASE}) SELECT * FROM x",
        f"SELECT (SELECT SUM(amount) FROM uploaded_data.payments) {BASE}",
        f"SELECT p.amount {BASE.replace('students s', 'payments s')}",
        f"SELECT p.amount {BASE.replace('students s', 'students p')}",
        f"SELECT payments.amount {BASE.replace('payments p', 'payments students')}",
        f"SELECT p.amount {BASE.replace('uploaded_data.students', 'public.students')}",
        f"SELECT p.amount {BASE.replace('students', 'other_workspace')}",
        f"SELECT p.amount {BASE.replace('students', 'other_owner')}",
        f"SELECT p.amount {BASE.replace('payments p', 'payments p(x,y,z)')}",
        f"SELECT p.amount {BASE.replace('uploaded_data.payments', 'ONLY uploaded_data.payments')}",
        f"SELECT p.amount {BASE.replace('payments p', chr(34) + 'PAYMENTS' + chr(34) + ' p')}",
        f"SELECT p.amount {BASE.replace('students s', chr(34) + 'students;DROP' + chr(34) + ' s')}",
        f"SELECT p.amount AS nonexistent {BASE} WHERE nonexistent>0",
        f"SELECT p.amount {BASE} WHERE EXISTS(SELECT p.id)",
        "SELECT p.amount "
        + BASE.replace("p.student_id=s.student_id", "COALESCE(p.student_id,0)=s.student_id"),
    ],
)
def test_unsafe_join_patterns_are_rejected_before_execution(sql: str) -> None:
    executor, gateway = Mock(), Mock()
    pipeline = TextToSqlPipeline(
        Mock(generate=Mock(return_value=sql)), join_validator(), executor, gateway
    )
    with pytest.raises(SqlValidationError):
        pipeline.run("Synthetic adversarial query")
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()


def test_no_relationship_keeps_single_table_policy() -> None:
    validator = SqlValidator({"payments": {"amount"}}, {"payments": "uploaded_data"}, max_tables=1)
    validator.validate("SELECT SUM(amount) FROM uploaded_data.payments")
    with pytest.raises(SqlValidationError):
        validator.validate(f"SELECT p.amount {BASE}")


def test_disabled_flag_rejects_even_backend_policies() -> None:
    validator = join_validator()
    validator._join_v1_enabled = False
    with pytest.raises(SqlValidationError, match="disabled"):
        validator.validate(f"SELECT p.amount {BASE}")
