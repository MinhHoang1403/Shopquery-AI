"""Relationship contracts reject untrusted identifiers and temporal mismatches."""

import pytest
from pydantic import ValidationError

from app.datasets.relationships import RelationshipConfirm, RelationshipInput


def test_confirmation_is_explicit_and_revision_bound() -> None:
    values = dict(
        source_table_id="1",
        source_column="student_id",
        target_table_id="2",
        target_column="student_id",
    )
    for confirmation in (False, 1, "true", None):
        with pytest.raises(ValidationError):
            RelationshipConfirm(**values, revision="a" * 64, confirmed=confirmation)
    with pytest.raises(ValidationError):
        RelationshipConfirm(**values, confirmed=True)
    assert RelationshipConfirm(**values, revision="a" * 64, confirmed=True).confirmed


def test_client_cannot_supply_physical_tables_sql_or_composite_keys() -> None:
    values = dict(source_table_id="1", source_column="id", target_table_id="2", target_column="id")
    for extra in ({"sql": "SELECT 1"}, {"physical_table_name": "someone_else"}):
        with pytest.raises(ValidationError):
            RelationshipInput(**values, **extra)
    with pytest.raises(ValidationError):
        RelationshipInput(**{**values, "source_column": ["id", "other"]})
