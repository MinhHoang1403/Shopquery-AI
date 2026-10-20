"""Only unambiguous identifier names are candidates; values alone are not intent."""

import pytest

from app.datasets.parser import ColumnSpec
from app.datasets.relationship_detection import relationship_candidates
from app.datasets.relationships import RelationshipTable


def table(identity, label, columns):
    return RelationshipTable(
        identity,
        f"table_{identity}",
        tuple(ColumnSpec(name, name, kind) for name, kind in columns),
        3,
        display_name=label,
    )


@pytest.mark.parametrize("key", ["id", "student_id"])
def test_named_foreign_identifier_targets_entity_not_generic_matching_values(key):
    tables = {
        "1": table("1", "students", [(key, "TEXT"), ("name", "TEXT")]),
        "2": table("2", "payments", [("student_id", "TEXT"), ("amount", "NUMERIC")]),
    }
    candidates = relationship_candidates(tables, "2")
    assert len(candidates) == 1
    assert candidates[0].source_table_id == "2"
    assert candidates[0].target_table_id == "1"
    assert candidates[0].target_column == key


@pytest.mark.parametrize(
    "domain,key",
    [("customers", "customer_code"), ("employees", "employee_id"), ("categories", "category_id")],
)
def test_detection_is_not_tuition_specific(domain, key):
    tables = {
        "1": table("1", domain, [(key, "BIGINT")]),
        "2": table("2", "events", [(key, "BIGINT")]),
    }
    assert len(relationship_candidates(tables, "1")) == 1


@pytest.mark.parametrize(
    "key,kind,label",
    [
        ("id", "BIGINT", "students"),
        ("student_id", "BOOLEAN", "students"),
        ("student_id", "DATE", "students"),
        ("student_id", "TEXT", "unrelated"),
    ],
)
def test_generic_keys_non_identifier_types_and_unrelated_names_are_not_inferred(key, kind, label):
    tables = {"1": table("1", label, [(key, kind)]), "2": table("2", "payments", [(key, kind)])}
    assert relationship_candidates(tables, "2") == []


def test_ambiguous_target_or_multiple_keys_stays_manual_before_reading_values():
    tables = {
        "1": table("1", "students", [("student_id", "TEXT")]),
        "2": table("2", "payments", [("student_id", "TEXT")]),
        "3": table("3", "students", [("student_id", "TEXT")]),
    }
    assert relationship_candidates(tables, "2") == []
    del tables["3"]
    tables["1"] = table("1", "students", [("id", "TEXT"), ("student_id", "TEXT")])
    assert relationship_candidates(tables, "2") == []


def test_existing_pair_not_resurrected_by_an_unrelated_upload_and_types_must_match():
    tables = {
        "1": table("1", "students", [("student_id", "TEXT")]),
        "2": table("2", "payments", [("student_id", "TEXT")]),
        "3": table("3", "notes", [("note_id", "TEXT")]),
    }
    assert relationship_candidates(tables, "3") == []
    tables["1"] = table("1", "students", [("student_id", "BIGINT")])
    assert relationship_candidates(tables, "2") == []


def test_automatic_provenance_cannot_pretend_to_be_a_manual_confirmation():
    from pydantic import ValidationError

    from app.datasets.relationships import RelationshipRecord

    values = dict(
        source_table_id="1",
        source_column="student_id",
        target_table_id="2",
        target_column="id",
        revision="a" * 64,
        relationship_id="synthetic",
        valid=True,
        cardinality="many-to-one",
        source_rows=3,
        target_rows=2,
        source_nulls=0,
        target_nulls=0,
        target_duplicates=0,
        orphan_rows=0,
        reasons=[],
    )
    with pytest.raises(ValidationError):
        RelationshipRecord(**values, origin="automatic", confirmed=True)
    with pytest.raises(ValidationError):
        RelationshipRecord(**values, origin="manual", confirmed=False)
