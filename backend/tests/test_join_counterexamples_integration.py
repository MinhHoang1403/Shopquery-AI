"""Independent PostgreSQL counterexamples, not string-equivalence assertions."""

import pytest
from sqlalchemy import text

from app.core.errors import SqlUnsupportedError
from app.database.session import get_setup_engine
from tests.test_auto_relationships_integration import workspace  # noqa: F401
from tests.test_dataset_parser import parse
from tests.test_three_table_join import validator

pytestmark = pytest.mark.integration


def test_label_only_sql_is_valid_but_merges_two_distinct_entities():
    with get_setup_engine().connect() as connection:
        bad = connection.execute(
            text(
                "SELECT d.name,SUM(f.v) FROM "
                "(VALUES ('D1',20::numeric),('D2',30::numeric)) f(id,v) "
                "INNER JOIN (VALUES ('D1','Same'),('D2','Same')) d(id,name) "
                "ON f.id=d.id GROUP BY d.name"
            )
        ).all()
        good = connection.execute(
            text(
                "SELECT id,SUM(v) FROM (VALUES ('D1',20::numeric),('D2',30::numeric)) f(id,v) "
                "GROUP BY id ORDER BY id"
            )
        ).all()
        plan = connection.scalar(
            text(
                "EXPLAIN (FORMAT JSON, ANALYZE, TIMING OFF) SELECT d.id, SUM(f.v) "
                "FROM (VALUES ('D1',20::numeric),('D2',30::numeric)) f(id,v) "
                "INNER JOIN (VALUES ('D1','Same'),('D2','Same')) d(id,name) "
                "ON f.id=d.id GROUP BY d.id"
            )
        )
    assert len(bad) == 1 and str(bad[0][1]) == "50"
    assert [(r[0], str(r[1])) for r in good] == [("D1", "20"), ("D2", "30")]
    assert plan[0]["Plan"]["Actual Rows"] == 2
    with pytest.raises(SqlUnsupportedError) as error:
        validator().validate(
            "SELECT s.name,SUM(p.amount) AS total FROM uploaded_data.payments p "
            "INNER JOIN uploaded_data.students s ON p.student_id=s.student_id GROUP BY s.name"
        )
    assert error.value.code == "join_grain"


@pytest.mark.parametrize(
    "dimension,fact",
    [
        (b"asset_id\n10\n10\n", b"asset_id,value\n10,1\n10,2\n"),
        (b"asset_id\n10\n20\n", b"asset_id,value\n10,1\n30,2\n10,3\n"),
        (b"asset_id\n10\n20\n", b"asset_id,value\n10,1\n,2\n20,3\n"),
        (b"asset_id,Name\n10,One\n,Missing\n", b"asset_id,value\n10,1\n10,2\n"),
        (b"asset_id\nA10\nA20\n", b"asset_id,value\n10,1\n20,2\n10,3\n"),
        (b"asset_id\n10\n20\n", b"asset_id,value\n10,1\n20,2\n"),
    ],
)
def test_unsafe_and_direction_ambiguous_data_do_not_activate_automatic_relations(
    workspace,  # noqa: F811
    dimension,
    fact,
):
    repository, dataset_id, relations = workspace
    repository.add_table(dataset_id, parse("assets.csv", dimension), auto_relationships=True)
    repository.add_table(dataset_id, parse("events.csv", fact), auto_relationships=True)
    assert relations.list(dataset_id) == []


def test_two_semantic_targets_are_manual_even_if_both_have_complete_matching_values(workspace):  # noqa: F811
    repository, dataset_id, relations = workspace
    for name in ("assets.csv", "ássets.csv"):
        repository.add_table(
            dataset_id, parse(name, b"asset_id,Name\nA1,One\nA2,Two\n"), auto_relationships=True
        )
    repository.add_table(
        dataset_id,
        parse("events.csv", b"asset_id,Value\nA1,1\nA1,2\nA2,3\n"),
        auto_relationships=True,
    )
    assert relations.list(dataset_id) == []
