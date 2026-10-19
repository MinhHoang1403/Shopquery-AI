"""Confirmed relationships stay in one owned workspace and reject unsafe keys."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.database.models import DatasetRelationship
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput
from app.datasets.repository import DatasetRepository
from app.text_to_sql.validator import ValidatedSql
from tests.auth_helpers import TEST_OWNER
from tests.test_dataset_parser import parse

pytestmark = pytest.mark.integration


@pytest.fixture
def linked_workspace():
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create_workspace(f"JOIN {uuid4()}")
    dataset = repository.add_table(
        dataset.dataset_id, parse("students.csv", b"Id,Name,Fee\n101,An,99\n102,Binh,88\n")
    )
    dataset = repository.add_table(
        dataset.dataset_id,
        parse("payments.csv", b"Id,Student id,Amount\n2,101,20.00\n3,101,0.00\n4,102,\n"),
    )
    source, target = dataset.tables[1], dataset.tables[0]
    request = RelationshipInput(
        source_table_id=str(source.dataset_table_id),
        source_column="student_id",
        target_table_id=str(target.dataset_table_id),
        target_column="id",
    )
    yield repository, dataset, request
    repository.delete(dataset.dataset_id, delete_conversations=True)


def test_preview_confirm_idempotency_and_deletion(linked_workspace) -> None:
    repository, dataset, request = linked_workspace
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    preview = relations.preview(dataset.dataset_id, request)
    assert preview.valid and preview.cardinality == "many-to-one"
    assert (preview.source_rows, preview.target_rows, preview.orphan_rows) == (3, 2, 0)
    assert relations.list(dataset.dataset_id) == []
    confirmation = RelationshipConfirm(
        **request.model_dump(), revision=preview.revision, confirmed=True
    )
    first = relations.confirm(dataset.dataset_id, confirmation)
    assert (
        relations.confirm(dataset.dataset_id, confirmation).relationship_id == first.relationship_id
    )
    assert len(relations.approved(dataset.dataset_id)) == 1
    with pytest.raises(ResourceNotFoundError):
        RelationshipRepository(get_setup_engine(), uuid4()).list(dataset.dataset_id)
    relations.delete(dataset.dataset_id, UUID(first.relationship_id))
    assert relations.approved(dataset.dataset_id) == ()
    assert repository.get(dataset.dataset_id).table_count == 2


@pytest.mark.parametrize(
    ("dimension", "fact", "reason"),
    [
        ("2\n2", "2\n2", "trùng"),
        ("2\n", "2\n3", "khóa đích"),
        ("2\n3", "2\n9", "khóa đích"),
        ("02\n03", "2\n3", "Kiểu"),
    ],
)
def test_full_key_validation_rejects_invalid_relations(
    dimension: str, fact: str, reason: str
) -> None:
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create_workspace(f"Bad JOIN {uuid4()}")
    try:
        dataset = repository.add_table(
            dataset.dataset_id, parse("dimension.csv", ("Key\n" + dimension).encode())
        )
        dataset = repository.add_table(
            dataset.dataset_id, parse("fact.csv", ("Key\n" + fact).encode())
        )
        relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
        request = RelationshipInput(
            source_table_id=str(dataset.tables[1].dataset_table_id),
            source_column="key",
            target_table_id=str(dataset.tables[0].dataset_table_id),
            target_column="key",
        )
        preview = relations.preview(dataset.dataset_id, request)
        assert not preview.valid and any(reason in message for message in preview.reasons)
        with pytest.raises(ResourceConflictError):
            relations.confirm(
                dataset.dataset_id,
                RelationshipConfirm(
                    **request.model_dump(),
                    revision=preview.revision,
                    confirmed=True,
                ),
            )
        assert not relations.list(dataset.dataset_id)
    finally:
        repository.delete(dataset.dataset_id)


@pytest.mark.parametrize("table_index", [0, 1])
def test_table_delete_cascades_only_related_metadata_and_stale_confirmation_fails(
    linked_workspace,
    table_index,
) -> None:
    repository, dataset, request = linked_workspace
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    preview = relations.preview(dataset.dataset_id, request)
    relations.confirm(
        dataset.dataset_id,
        RelationshipConfirm(**request.model_dump(), revision=preview.revision, confirmed=True),
    )
    repository.delete_table(dataset.dataset_id, dataset.tables[table_index].dataset_table_id)
    assert relations.list(dataset.dataset_id) == []
    with pytest.raises(ResourceNotFoundError):
        relations.confirm(
            dataset.dataset_id,
            RelationshipConfirm(**request.model_dump(), revision=preview.revision, confirmed=True),
        )
    with Session(get_setup_engine()) as session:
        assert (
            session.scalar(
                select(DatasetRelationship).where(
                    DatasetRelationship.dataset_id == dataset.dataset_id
                )
            )
            is None
        )


def test_cross_workspace_and_changed_revision_fail_closed(linked_workspace) -> None:
    repository, dataset, request = linked_workspace
    other = repository.create("Other JOIN " + str(uuid4()), parse("other.csv", b"Id\n101\n102\n"))
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    try:
        for invalid in (
            request.model_copy(update={"source_column": "missing"}),
            request.model_copy(update={"target_table_id": request.source_table_id}),
        ):
            with pytest.raises(ResourceNotFoundError):
                relations.preview(dataset.dataset_id, invalid)
        with pytest.raises(IntegrityError), get_setup_engine().begin() as connection:
            connection.execute(
                DatasetRelationship.__table__.insert(),
                {
                    "relationship_id": uuid4(),
                    "dataset_id": dataset.dataset_id,
                    "source_table_id": dataset.tables[1].dataset_table_id,
                    "source_column": request.source_column,
                    "target_table_id": other.table.dataset_table_id,
                    "target_column": "id",
                    "revision": "0" * 64,
                    "statistics": {},
                },
            )
        with pytest.raises(ResourceNotFoundError):
            relations.preview(
                dataset.dataset_id,
                request.model_copy(
                    update={
                        "target_table_id": str(other.table.dataset_table_id),
                    }
                ),
            )
        with pytest.raises(ResourceConflictError):
            relations.confirm(
                dataset.dataset_id,
                RelationshipConfirm(
                    **request.model_dump(),
                    revision="0" * 64,
                    confirmed=True,
                ),
            )
        preview = relations.preview(dataset.dataset_id, request)
        relations.confirm(
            dataset.dataset_id,
            RelationshipConfirm(**request.model_dump(), revision=preview.revision, confirmed=True),
        )
        with get_setup_engine().begin() as connection:
            connection.execute(
                text("UPDATE dataset_tables SET row_count=row_count+1 WHERE dataset_table_id=:id"),
                {"id": dataset.tables[0].dataset_table_id},
            )
        assert not relations.list(dataset.dataset_id)[0].valid
        assert not relations.approved(dataset.dataset_id)
    finally:
        repository.delete(other.dataset_id)


def test_workspace_deletion_cascades_relationships_not_other_workspace():
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create("Delete linked " + str(uuid4()), parse("dim.csv", b"Id\n101\n"))
    other = repository.create_workspace("Keep other " + str(uuid4()))
    try:
        dataset = repository.add_table(dataset.dataset_id, parse("fact.csv", b"Key\n101\n101\n"))
        request = RelationshipInput(
            source_table_id=str(dataset.tables[1].dataset_table_id),
            source_column="key",
            target_table_id=str(dataset.tables[0].dataset_table_id),
            target_column="id",
        )
        repo = RelationshipRepository(get_setup_engine(), TEST_OWNER)
        preview = repo.preview(dataset.dataset_id, request)
        repo.confirm(
            dataset.dataset_id,
            RelationshipConfirm(
                **request.model_dump(),
                revision=preview.revision,
                confirmed=True,
            ),
        )
        repository.delete(dataset.dataset_id)
        with get_setup_engine().connect() as connection:
            assert not connection.scalar(
                select(DatasetRelationship.relationship_id).where(
                    DatasetRelationship.dataset_id == dataset.dataset_id,
                )
            )
        assert repository.get(other.dataset_id)
    finally:
        if any(item.dataset_id == dataset.dataset_id for item in repository.list()):
            repository.delete(dataset.dataset_id)
        repository.delete(other.dataset_id)


@pytest.mark.parametrize(
    ("dimension", "fact", "expected"),
    [
        ("101,A\n,B\n", "101,2\n", (0, 1, 0, 0)),
        ("101,A\n102,B\n", "101,2\n,3\n", (1, 0, 0, 0)),
        ("101,A\n102,B\n", "101,2\n102,3\n", (0, 0, 0, 0)),
        ("101,A\n101,B\n", "101,2\n101,3\n", (0, 0, 1, 0)),
        ("101,A\n", "101,2\n" * 20 + "999,3\n", (0, 0, 0, 1)),
        ("101,A\n" + "102,B\n" * 20, "101,2\n", (0, 0, 19, 0)),
    ],
)
def test_nulls_one_to_one_many_to_many_and_rows_beyond_preview(dimension, fact, expected):
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create_workspace("Full scan " + str(uuid4()))
    try:
        dataset = repository.add_table(
            dataset.dataset_id, parse("dimension.csv", ("Key,Name\n" + dimension).encode())
        )
        dataset = repository.add_table(
            dataset.dataset_id, parse("fact.csv", ("Key,Amount\n" + fact).encode())
        )
        request = RelationshipInput(
            source_table_id=str(dataset.tables[1].dataset_table_id),
            source_column="key",
            target_table_id=str(dataset.tables[0].dataset_table_id),
            target_column="key",
        )
        preview = RelationshipRepository(get_setup_engine(), TEST_OWNER).preview(
            dataset.dataset_id, request
        )
        assert (
            preview.source_nulls,
            preview.target_nulls,
            preview.target_duplicates,
            preview.orphan_rows,
        ) == expected
        assert preview.valid == (expected == (0, 0, 0, 0))
        if preview.valid:
            assert preview.cardinality == "one-to-one"
    finally:
        repository.delete(dataset.dataset_id)


def test_parallel_confirm_and_execution_guard_serialize_deletion(linked_workspace):
    repository, dataset, request = linked_workspace
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    preview = relations.preview(dataset.dataset_id, request)
    confirmation = RelationshipConfirm(
        **request.model_dump(), revision=preview.revision, confirmed=True
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(relations.confirm, dataset.dataset_id, confirmation) for _ in range(2)
        ]
        ids = [future.result(timeout=5).relationship_id for future in futures]
    assert ids[0] == ids[1] and len(relations.list(dataset.dataset_id)) == 1
    approved = relations.approved(dataset.dataset_id)
    sql = ValidatedSql("SELECT 1", frozenset(), ids[0])
    started = Event()

    def remove_table():
        started.set()
        repository.delete_table(dataset.dataset_id, dataset.tables[0].dataset_table_id)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with relations.execution_guard(dataset.dataset_id, approved, sql):
            future = pool.submit(remove_table)
            assert started.wait(1)
            # The deleting transaction cannot obtain FOR UPDATE while execution owns FOR SHARE.
            with pytest.raises(TimeoutError):
                future.result(timeout=0.15)
            assert repository.get(dataset.dataset_id).table_count == 2
        future.result(timeout=5)
    assert not relations.list(dataset.dataset_id)
    with (
        pytest.raises(ResourceConflictError),
        relations.execution_guard(dataset.dataset_id, approved, sql),
    ):
        pytest.fail("Stale relationship reached executor")


def test_removed_relationship_and_changed_metadata_block_executor(linked_workspace):
    repository, dataset, request = linked_workspace
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    preview = relations.preview(dataset.dataset_id, request)
    confirmation = RelationshipConfirm(
        **request.model_dump(), revision=preview.revision, confirmed=True
    )
    record = relations.confirm(dataset.dataset_id, confirmation)
    approved = relations.approved(dataset.dataset_id)
    sql = ValidatedSql("SELECT 1", frozenset(), record.relationship_id)
    relations.delete(dataset.dataset_id, UUID(record.relationship_id))
    with (
        pytest.raises(ResourceConflictError),
        relations.execution_guard(dataset.dataset_id, approved, sql),
    ):
        pytest.fail("Deleted relationship reached executor")
    record = relations.confirm(dataset.dataset_id, confirmation)
    approved = relations.approved(dataset.dataset_id)
    sql.relationship_id = record.relationship_id
    with get_setup_engine().begin() as connection:
        connection.execute(
            text("UPDATE dataset_tables SET row_count=row_count+1 WHERE dataset_table_id=:id"),
            {"id": dataset.tables[0].dataset_table_id},
        )
    with (
        pytest.raises(ResourceConflictError),
        relations.execution_guard(dataset.dataset_id, approved, sql),
    ):
        pytest.fail("Changed source reached executor")
