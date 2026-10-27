"""Read-only PostgreSQL oracles and registered-document scopes in isolated CI only."""

import csv
import io
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import ModelResponseError, ResourceNotFoundError
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput
from app.datasets.repository import DatasetRepository
from app.dependencies import _build_dataset_chat_service, build_workspace_context
from app.rag.repository import DocumentRepository
from app.rag.upload_parser import parse_document_file
from app.routing.router import RouteDecision, RouteLabel
from tests.auth_helpers import TEST_OWNER
from tests.test_dataset_parser import parse
from tests.test_policy_document_scope import regulation

pytestmark = pytest.mark.integration


def csv_content(headers, rows):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode()


@pytest.mark.parametrize(
    "entity,metric,identity,threshold,values",
    [
        ("cơ sở", "value_amount", "site_key", "75,50", ["75.49", "75.50", "75.51"]),
        ("trạm", "charge_total", "location_key", "12,01", ["12.00", "12.01", "12.02"]),
        ("khách sạn", "booking_amount", "hotel_key", "9.876,54", ["9876.53", "9876.54", "9876.55"]),
    ],
)
@pytest.mark.parametrize("outside_period", [False, True])
def test_complete_regulation_and_full_row_scope_have_independent_pg_evidence(
    monkeypatch, entity, metric, identity, threshold, values, outside_period
):
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create_workspace("Scoped synthetic " + uuid4().hex)
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    try:
        dataset = repository.add_table(
            dataset.dataset_id,
            parse(
                "01_" + entity + ".csv",
                csv_content([identity, "name"], [(f"E{i}", f"Entity {i}") for i in range(3)]),
            ),
        )
        dataset = repository.add_table(
            dataset.dataset_id,
            parse(
                "02_sự_kiện.csv",
                csv_content(
                    ["record_key", identity, metric, "event_date", "state"],
                    [
                        (
                            f"R{i}",
                            f"E{i}",
                            value,
                            "2032-04-25" if outside_period and i == 0 else "2032-04-24",
                            "Xác nhận",
                        )
                        for i, value in enumerate(values)
                    ],
                ),
            ),
        )
        dimension = next(t for t in dataset.tables if t.display_name != "02_sự_kiện")
        fact = next(t for t in dataset.tables if t.display_name == "02_sự_kiện")
        proposal = RelationshipInput(
            source_table_id=str(fact.dataset_table_id),
            source_column=identity,
            target_table_id=str(dimension.dataset_table_id),
            target_column=identity,
        )
        preview = relations.preview(dataset.dataset_id, proposal)
        relations.confirm(
            dataset.dataset_id,
            RelationshipConfirm(**proposal.model_dump(), revision=preview.revision, confirmed=True),
        )
        embedder = Mock(
            embed_document=Mock(return_value=[1.0, *([0.0] * 767)]),
            embed_query=Mock(return_value=[1.0, *([0.0] * 767)]),
        )
        documents = DocumentRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
        info = documents.add_document(
            dataset.dataset_id,
            parse_document_file(
                "policy.txt", regulation(entity, metric, identity, threshold).encode()
            ),
            embedder,
        )
        assert info.chunk_count == 2
        monkeypatch.setattr("app.dependencies.build_embedding_gateway", lambda _: embedder)
        settings = get_settings().model_copy(update={"sql_join_v1_enabled": True})
        context = build_workspace_context(settings, repository.get(dataset.dataset_id), repository)
        assert context.column_profiles[fact.physical_table_name]["event_date"][0:2] == (3, 3)
        with pytest.raises(ResourceNotFoundError):
            DatasetRepository(get_setup_engine(), get_readonly_engine(), uuid4()).column_profiles(
                dataset
            )
        gateway = Mock(
            generate_structured=Mock(
                return_value=RouteDecision(
                    route=RouteLabel.HYBRID,
                    reason="synthetic typed intent",
                    policy_intent="all",
                    policy_scope="all_entities",
                )
            )
        )
        service = _build_dataset_chat_service(settings, context, gateway)
        if outside_period:
            with pytest.raises(ModelResponseError):
                service.chat("Đánh giá chính sách cho toàn bộ đối tượng.")
            assert gateway.generate_structured.call_count == 1
            return
        result = service.chat("Đánh giá chính sách cho toàn bộ đối tượng.")
        assert result.verification_status == "verified_classification"
        with get_readonly_engine().connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            expected = [
                dict(r)
                for r in connection.execute(
                    text(
                        f'SELECT d."{identity}" AS entity_id, '
                        f'SUM(f."{metric}")::text AS metric_value '
                        f'FROM uploaded_data."{fact.physical_table_name}" f '
                        f'JOIN uploaded_data."{dimension.physical_table_name}" d '
                        f'USING("{identity}") '
                        f'GROUP BY d."{identity}"'
                    )
                ).mappings()
            ]
        assert {r["entity_id"]: r for r in result.rows} == {r["entity_id"]: r for r in expected}
        boundary = Decimal(threshold.replace(".", "").replace(",", "."))
        assert [
            r["entity_id"]
            for r in sorted(expected, key=lambda r: r["entity_id"])
            if Decimal(r["metric_value"]) >= boundary
        ] == ["E1", "E2"]
        assert "Chưa đạt: E0." in result.answer and "Đạt: E1, E2." in result.answer
        assert len(result.sources) == 2
        assert gateway.generate_structured.call_count == 1
        assert embedder.embed_query.call_count == 1
    finally:
        repository.delete(dataset.dataset_id, delete_conversations=True)
