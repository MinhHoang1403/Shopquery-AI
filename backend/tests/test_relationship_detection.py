"""Only unambiguous identifier names are candidates; values alone are not intent."""

from itertools import cycle
from unittest.mock import MagicMock

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


def ev_tables():
    return {
        "1": table("1", "01_tram_sac", [("ma_tram", "TEXT"), ("ten_tram", "TEXT")]),
        "2": table("2", "02_goi_sac", [("ma_goi", "TEXT"), ("ten_goi", "TEXT")]),
        "3": table(
            "3",
            "03_phien_sac",
            [
                ("ma_phien", "TEXT"),
                ("ma_tram", "TEXT"),
                ("ma_goi", "TEXT"),
            ],
        ),
    }


def verification_connection(source=(3, 3, 2), target=(2, 2, 2), orphans=0):
    connection = MagicMock()
    connection.execute.return_value.one.side_effect = cycle([source, target])
    connection.scalar.return_value = orphans
    return connection


def test_ev_discovery_uses_identifier_and_dimension_label_metadata():
    from app.datasets.relationship_detection import discover_relationships

    tables = ev_tables()
    candidates = relationship_candidates(tables, "3")
    assert {(r.source_table_id, r.target_table_id, r.source_column) for r in candidates} == {
        ("3", "1", "ma_tram"),
        ("3", "2", "ma_goi"),
    }
    result = discover_relationships(verification_connection(), tables, None, set())
    assert len(result.automatic) == 2 and result.suggestions == []
    assert all(p.valid and p.cardinality == "many-to-one" for p in result.automatic)


@pytest.mark.parametrize(
    "key,label",
    [
        ("customer_id", "customers"),
        ("employee_id", "employees"),
        ("student_id", "students"),
        ("customerId", "01 Customer Catalog"),
        ("CustomerID", "Customer"),
        ("Mã Học Viên", "01 Danh sách Học Viên"),
        ("hocVienMa", "DanhSachHocVien"),
        ("customerCode", "Customer"),
        ("customer_ref", "Customer"),
        ("customerKey", "Customer"),
        ("customer_number", "Customer"),
        ("customer_no", "Customer"),
    ],
)
def test_naming_patterns_use_original_headers_without_changing_sql_identifiers(key, label):
    tables = {
        "1": table("1", label, [("key_value", "TEXT"), ("name", "TEXT")]),
        "2": table("2", "events", [("foreign_key", "TEXT")]),
    }
    for identity, column_name in (("1", "key_value"), ("2", "foreign_key")):
        item = tables[identity]
        tables[identity] = RelationshipTable(
            item.table_id,
            item.physical_name,
            (ColumnSpec(key, column_name, "TEXT"), *item.columns[1:]),
            item.row_count,
            display_name=item.display_name,
        )
    candidates = relationship_candidates(tables, "2")
    assert len(candidates) == 1
    assert candidates[0].source_column == "foreign_key"
    assert candidates[0].target_column == "key_value"


@pytest.mark.parametrize(
    "source,target,orphans",
    [
        ((3, 2, 2), (2, 2, 2), 0),
        ((3, 3, 2), (2, 1, 1), 0),
        ((3, 3, 2), (3, 3, 2), 0),
        ((3, 3, 2), (2, 2, 2), 1),
        ((0, 0, 0), (2, 2, 2), 0),
    ],
)
def test_full_verifier_still_rejects_null_duplicates_orphans_and_empty_keys(
    source,
    target,
    orphans,
):
    from app.datasets.relationship_detection import discover_relationships

    result = discover_relationships(
        verification_connection(source, target, orphans),
        ev_tables(),
        None,
        set(),
    )
    assert result.automatic == []
    assert len(result.suggestions) == 2
    assert all(not item.preview.valid for item in result.suggestions)


def test_one_to_one_cannot_choose_fact_direction_and_rescan_skips_existing_pairs():
    from app.datasets.relationship_detection import discover_relationships

    result = discover_relationships(
        verification_connection((2, 2, 2), (2, 2, 2)),
        ev_tables(),
        None,
        set(),
    )
    assert result.automatic == [] and len(result.suggestions) == 2
    result = discover_relationships(
        verification_connection(),
        ev_tables(),
        None,
        {frozenset({"1", "3"})},
    )
    assert len(result.automatic) == 1 and result.automatic[0].target_table_id == "2"


def test_competing_targets_are_suggestions_even_if_one_name_ranks_higher():
    from app.datasets.relationship_detection import discover_relationships

    tables = ev_tables()
    tables["4"] = table("4", "tram", [("ma_tram", "TEXT")])
    result = discover_relationships(verification_connection(), tables, "3", set())
    assert [p.source_column for p in result.automatic] == ["ma_goi"]
    assert len(result.suggestions) == 2


def test_identifier_families_and_number_context_are_not_interchangeable():
    tables = {
        "1": table("1", "customers", [("customer_code", "TEXT")]),
        "2": table("2", "events", [("customer_id", "TEXT")]),
    }
    assert relationship_candidates(tables, "2") == []
    for identity in tables:
        tables[identity] = table(identity, tables[identity].display_name, [("customer_no", "TEXT")])
    assert relationship_candidates(tables, "2") == []


def test_cycle_is_not_broken_by_arbitrarily_selecting_a_path():
    from app.datasets.relationship_detection import discover_relationships

    tables = {
        "1": table("1", "customers", [("employee_id", "TEXT"), ("region_id", "TEXT")]),
        "2": table("2", "employees", [("employee_id", "TEXT"), ("region_id", "TEXT")]),
        "3": table("3", "regions", [("region_id", "TEXT")]),
    }
    result = discover_relationships(verification_connection(), tables, None, set())
    assert result.automatic == [] and len(result.suggestions) == 3


def test_scan_limit_and_deadline_do_not_auto_approve_a_partial_search(monkeypatch):
    import app.datasets.relationship_detection as detection

    tables = {"1": table("1", "customers", [("id", "TEXT")])}
    tables.update(
        {
            str(i): table(str(i), "events", [("customer_id", "TEXT")])
            for i in range(2, 2 + detection.MAX_DISCOVERY_CHECKS + 1)
        }
    )
    connection = verification_connection()
    result = detection.discover_relationships(connection, tables, None, set())
    assert result.truncated and result.automatic == []
    assert len(result.suggestions) == detection.MAX_DISCOVERY_CHECKS
    ticks = iter([0, 0, detection.MAX_DISCOVERY_SECONDS + 1])
    monkeypatch.setattr(detection, "monotonic", lambda: next(ticks))
    result = detection.discover_relationships(verification_connection(), ev_tables(), None, set())
    assert result.truncated and result.automatic == [] and len(result.suggestions) == 1


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


@pytest.mark.parametrize(
    "label,key",
    [
        ("02_tai_xe", "tai_xe_id"),
        ("02_customers", "customer_code"),
    ],
)
def test_numbered_exact_entity_labels_keep_explicit_key_evidence(label, key):
    tables = {
        "1": table("1", label, [(key, "TEXT"), ("name", "TEXT")]),
        "2": table("2", "03_events", [(key, "TEXT"), ("amount", "NUMERIC")]),
    }
    candidates = relationship_candidates(tables, "2")
    assert len(candidates) == 1
    assert candidates[0].target_table_id == "1"
    assert candidates[0].target_column == key


@pytest.mark.parametrize(
    "label,columns",
    [
        ("01_kho_dieu_phoi", [("id", "TEXT")]),
        ("01_kho_dieu_phoi", [("kho_id", "TEXT")]),
        ("01. Kho điều phối", [("kho_id", "TEXT")]),
        ("01_kho_dieu_phoi", [("kho_id", "TEXT"), ("event_id", "TEXT")]),
        ("01_luu_kho", [("kho_id", "TEXT")]),
        ("01_khoa_hoc", [("kho_id", "TEXT")]),
    ],
)
def test_descriptive_labels_require_exact_entity_boundary_and_one_explicit_identifier(
    label, columns
):
    tables = {
        "1": table("1", label, columns),
        "2": table("2", "events", [("kho_id", "TEXT")]),
    }
    assert relationship_candidates(tables, "2") == []


def test_numbered_descriptive_targets_cannot_choose_between_two_matching_tables():
    tables = {
        "1": table("1", "01_kho_dieu_phoi", [("kho_id", "TEXT")]),
        "2": table("2", "02_kho_du_phong", [("kho_id", "TEXT")]),
        "3": table("3", "events", [("kho_id", "TEXT")]),
    }
    assert relationship_candidates(tables, "3") == []


def test_upload_scope_does_not_hide_a_competing_existing_dimension():
    from app.datasets.relationship_detection import discover_relationships

    tables = ev_tables()
    tables["4"] = table("4", "tram", [("ma_tram", "TEXT")])
    assert relationship_candidates(tables, "4") == []
    result = discover_relationships(verification_connection(), tables, "4", set())
    assert result.automatic == []
    assert any(
        item.relationship.source_table_id == "3" and item.relationship.target_table_id == "4"
        for item in result.suggestions
    )


def test_equal_values_without_identifier_semantics_never_trigger_data_scans():
    from app.datasets.relationship_detection import discover_relationships

    tables = {
        "1": table("1", "warehouses", [("id", "TEXT"), ("status", "TEXT")]),
        "2": table("2", "students", [("id", "TEXT"), ("status", "TEXT")]),
    }
    connection = verification_connection()
    result = discover_relationships(connection, tables, None, set())
    assert result.automatic == [] and result.suggestions == []
    connection.execute.assert_not_called()


def test_descriptive_target_with_other_identifier_roles_needs_confirmation():
    tables = {
        "1": table(
            "1",
            "kho_dieu_phoi",
            [
                ("kho_id", "TEXT"),
                ("ten_kho", "TEXT"),
                ("event_id", "TEXT"),
            ],
        ),
        "2": table("2", "events", [("kho_id", "TEXT")]),
    }
    assert relationship_candidates(tables, "2") == []
