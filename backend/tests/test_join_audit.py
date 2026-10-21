"""Semantic counterexamples must fail before any SQL execution or grounding."""

import pytest

from app.core.errors import SqlUnsupportedError
from app.datasets.parser import ColumnSpec
from app.datasets.relationship_detection import relationship_candidates
from app.datasets.relationships import RelationshipTable
from tests.test_three_table_join import validator


@pytest.mark.parametrize("three", [False, True])
def test_entity_label_without_verified_identity_is_not_a_safe_group(three):
    sql = (
        "SELECT s.name, SUM(p.amount) AS total FROM uploaded_data.payments p "
        "INNER JOIN uploaded_data.students s ON p.student_id=s.student_id "
        + ("INNER JOIN uploaded_data.courses c ON s.course_id=c.course_id " if three else "")
        + "GROUP BY s.name"
    )
    with pytest.raises(SqlUnsupportedError) as caught:
        validator().validate(sql)
    assert caught.value.code == "join_grain"


@pytest.mark.parametrize("aggregate", ["SUM", "AVG"])
def test_verified_fact_identifier_is_not_a_measure_just_because_it_is_numeric(aggregate):
    from app.text_to_sql.join_policy import ApprovedJoin
    from app.text_to_sql.validator import SqlValidator

    types = {"events": {"entity_id": "BIGINT"}, "entities": {"id": "BIGINT"}}
    checked = SqlValidator(
        {name: set(cols) for name, cols in types.items()},
        {name: "uploaded_data" for name in types},
        max_tables=2,
        approved_joins=(ApprovedJoin("one", "events", "entity_id", "entities", "id", "r"),),
        column_types=types,
        join_v1_enabled=True,
    )
    with pytest.raises(SqlUnsupportedError) as caught:
        checked.validate(
            f"SELECT {aggregate}(f.entity_id) AS total FROM uploaded_data.events f "
            "INNER JOIN uploaded_data.entities d ON f.entity_id=d.id"
        )
    assert caught.value.aggregate_reason == "identifier_measure"


def test_matching_values_and_descriptive_name_do_not_authorize_an_archival_entity():
    tables = {
        "1": RelationshipTable(
            "1",
            "archived",
            (ColumnSpec("Student id", "student_id", "TEXT"),),
            2,
            display_name="01_student_archive",
        ),
        "2": RelationshipTable(
            "2",
            "events",
            (ColumnSpec("Student id", "student_id", "TEXT"),),
            3,
            display_name="events",
        ),
    }
    assert relationship_candidates(tables, "2") == []


@pytest.mark.parametrize("alias", ["fact_row_count", "matched_row_count", "fact_value_count"])
def test_measure_cannot_impersonate_reserved_count_semantics(alias):
    with pytest.raises(SqlUnsupportedError) as caught:
        validator().validate(
            f"SELECT SUM(p.amount) AS {alias} FROM uploaded_data.payments p "
            "INNER JOIN uploaded_data.students s ON p.student_id=s.student_id"
        )
    assert caught.value.aggregate_reason == "count_semantics"


@pytest.mark.parametrize(
    "group",
    [
        "s.student_id, s.name WITH ROLLUP",
        "ROLLUP(s.student_id, s.name)",
        "GROUPING SETS ((s.student_id, s.name), (s.name))",
        "CUBE(s.student_id, s.name)",
    ],
)
def test_subtotals_cannot_bypass_entity_identity(group):
    with pytest.raises(SqlUnsupportedError) as caught:
        validator().validate(
            "SELECT s.name, SUM(p.amount) AS total FROM uploaded_data.payments p "
            "INNER JOIN uploaded_data.students s ON p.student_id=s.student_id "
            f"GROUP BY {group}"
        )
    assert caught.value.code == "join_grain"


@pytest.mark.parametrize("group", ["1, 2", "entity, label"])
def test_explicit_identity_can_use_projection_positions_or_safe_aliases(group):
    checked = validator().validate(
        "SELECT s.student_id AS entity, s.name AS label, SUM(p.amount) AS total "
        "FROM uploaded_data.payments p INNER JOIN uploaded_data.students s "
        f"ON p.student_id=s.student_id GROUP BY {group}"
    )
    assert checked
