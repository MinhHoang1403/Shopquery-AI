"""Projection aliases never authorize missing input columns."""

from unittest.mock import Mock

import pytest

from app.core.errors import SqlValidationError
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.validator import SqlValidator


@pytest.fixture(params=[("uploaded_data", "dataset_safe"), ("pg_temp", "table_1")])
def scope(request: pytest.FixtureRequest) -> tuple[SqlValidator, str]:
    schema, name = request.param
    return SqlValidator(
        {name: {"amount", "label"}}, {name: schema}, max_tables=1
    ), f"{schema}.{name}"


@pytest.mark.parametrize(
    "query",
    [
        "SELECT salary AS salary FROM {table}",
        "SELECT amount AS salary FROM {table} WHERE salary > 0",
        "SELECT amount AS salary FROM {table} GROUP BY salary + 1",
        "SELECT amount AS salary FROM {table} ORDER BY salary + 1",
        "SELECT amount AS salary FROM {table} HAVING salary > 0",
        "SELECT amount AS x, label AS x FROM {table} ORDER BY x",
        "SELECT amount AS x, label AS x FROM {table} GROUP BY x",
        "SELECT other.amount FROM {table}",
        "SELECT private.{name}.amount FROM {table}",
        "SELECT amount, SUM(amount) OVER () AS total FROM {table}",
        "SELECT amount FROM {table}; DELETE FROM {table}",
    ],
)
def test_rejects_invalid_alias_inputs_before_execution(
    scope: tuple[SqlValidator, str],
    query: str,
) -> None:
    validator, table = scope
    with pytest.raises(SqlValidationError):
        validator.validate(query.format(table=table, name=table.split(".")[1]))


@pytest.mark.parametrize(
    "query",
    [
        "SELECT amount AS salary FROM {table} ORDER BY salary DESC",
        "SELECT label AS group_label, SUM(amount) AS total FROM {table} "
        "GROUP BY group_label ORDER BY total",
        "SELECT amount AS amount FROM {table} GROUP BY amount ORDER BY amount",
        "SELECT label AS amount, COUNT(*) FROM {table} GROUP BY label ORDER BY amount",
        "SELECT amount AS total FROM {table} ORDER BY amount + 1",
        "SELECT t.amount AS salary FROM {table} t ORDER BY salary",
        "SELECT amount AS x, amount AS x FROM {table} ORDER BY x",
        "SELECT amount AS x, amount AS x FROM {table} GROUP BY x",
    ],
)
def test_keeps_valid_standalone_order_and_group_aliases(
    scope: tuple[SqlValidator, str],
    query: str,
) -> None:
    validator, table = scope
    assert validator.validate(query.format(table=table)).tables


def test_ambiguous_input_cannot_be_hidden_by_group_or_projection_alias() -> None:
    validator = SqlValidator({"a": {"id"}, "b": {"id"}})
    for sql in [
        "SELECT id AS id FROM a JOIN b ON a.id=b.id",
        "SELECT a.id AS id FROM a JOIN b ON a.id=b.id GROUP BY id",
        "SELECT x.id FROM a x JOIN b x ON x.id=x.id",
        "SELECT id AS id FROM a x JOIN a y ON x.id=y.id",
    ]:
        with pytest.raises(SqlValidationError):
            validator.validate(sql)
    validator.validate("SELECT a.id AS id FROM a JOIN b ON a.id=b.id ORDER BY id")


def test_table_alias_hides_the_original_qualifier() -> None:
    validator = SqlValidator({"a": {"id"}})
    with pytest.raises(SqlValidationError):
        validator.validate("SELECT a.id FROM a AS x")


def test_missing_projection_input_stops_pipeline_before_execution_or_answer(
    scope: tuple[SqlValidator, str],
) -> None:
    validator, table = scope
    generator, executor, gateway = Mock(), Mock(), Mock()
    generator.generate.return_value = f"SELECT salary AS salary FROM {table}"
    with pytest.raises(SqlValidationError):
        TextToSqlPipeline(generator, validator, executor, gateway).run("Lương?")
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()
