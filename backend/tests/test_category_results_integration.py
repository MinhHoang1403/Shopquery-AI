"""Category pairs stay at their requested grain under approved star joins."""

import csv
import io
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput
from app.datasets.repository import DatasetRepository
from app.dependencies import _build_dataset_chat_service, build_workspace_context
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.query_plan import PlanDecision, PlanExpression, PlanField, QueryPlan
from tests.auth_helpers import TEST_OWNER
from tests.test_dataset_parser import parse
from tests.test_plan_providers import gateway_harness, response
from tests.test_query_compiler import field, source

pytestmark = pytest.mark.integration


def csv_bytes(header, rows):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_three_table_categories_merge_entities_and_keep_exact_fact_totals(monkeypatch, provider):
    repo = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repo.create_workspace("Category fixture " + uuid4().hex)
    oracle = {}
    hotels = [(f"H{i}", f"Hotel {i}", f"Area {i % 3}", 80 + i * 2) for i in range(24)]
    rooms = [(f"R{i}", f"Class {i % 4}") for i in range(48)]
    facts = []
    for i in range(2400):
        h = i % 24
        r = (i // 24) % 48
        amount = None if i % 17 == 0 else Decimal(i % 101) / 100
        facts.append((f"B{i}", f"H{h}", f"R{r}", amount))
        key = (f"Area {h % 3}", f"Class {r % 4}")
        count, total = oracle.get(key, (0, Decimal("0.00")))
        oracle[key] = (count + 1, total + (amount or Decimal("0")))
    try:
        for name, header, rows in [
            ("hotels.csv", ["hotel_id", "hotel_name", "area", "rooms"], hotels),
            ("classes.csv", ["class_id", "room_class"], rooms),
            ("bookings.csv", ["booking_id", "hotel_id", "class_id", "amount"], facts),
        ]:
            dataset = repo.add_table(dataset.dataset_id, parse(name, csv_bytes(header, rows)))
        tables = {t.display_name: t for t in dataset.tables}
        relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
        for dim, key in [("hotels", "hotel_id"), ("classes", "class_id")]:
            request = RelationshipInput(
                source_table_id=str(tables["bookings"].dataset_table_id),
                source_column=key,
                target_table_id=str(tables[dim].dataset_table_id),
                target_column=key,
            )
            preview = relations.preview(dataset.dataset_id, request)
            relations.confirm(
                dataset.dataset_id,
                RelationshipConfirm(
                    **request.model_dump(), revision=preview.revision, confirmed=True
                ),
            )
        settings = get_settings().model_copy(update={"sql_join_v1_enabled": True})
        context = build_workspace_context(settings, dataset, repo)
        compiler = QueryCompiler(context)
        hotel, room, fact = (
            tables[k].physical_table_name for k in ["hotels", "classes", "bookings"]
        )
        plan = QueryPlan(
            source=source(compiler, fact),
            grouping="category",
            fields=[
                PlanField(reference=field(compiler, hotel, "area"), alias="area"),
                PlanField(reference=field(compiler, room, "room_class"), alias="room_class"),
                PlanField(reference="e0", alias="bookings"),
                PlanField(reference="e1", alias="total"),
            ],
            expressions=[
                PlanExpression(operation="row_count"),
                PlanExpression(operation="sum", arguments=[field(compiler, fact, "amount")]),
            ],
            group_by=[field(compiler, hotel, "area"), field(compiler, room, "room_class")],
            relationships=list(compiler.references.relationships),
        )
        gateway, calls = gateway_harness(
            monkeypatch,
            provider,
            [
                response(provider, '{"route":"SQL","reason":"Categories"}'),
                response(provider, PlanDecision(plan=plan).model_dump_json()),
            ],
        )
        try:
            result = _build_dataset_chat_service(settings, context, gateway).chat(
                "Count bookings and sum amount by area and room class"
            )
        finally:
            gateway.close()
        assert len(result.rows) == len(oracle) == 12
        assert {
            (r["area"], r["room_class"]): (r["bookings"], Decimal(r["total"])) for r in result.rows
        } == oracle
        assert sum(r["bookings"] for r in result.rows) == 2400 and len(calls) == 2
        assert result.sql.count("JOIN") == 2
        # A separate simple numeric filter must stay single-table for all paraphrases.
        expected = sorted(row[1] for row in hotels if row[3] > 100)
        from app.text_to_sql.executor import SqlExecutor
        from app.text_to_sql.query_plan import PlanFilter

        filtered = QueryPlan(
            source=source(compiler, hotel),
            fields=[PlanField(reference=field(compiler, hotel, "hotel_name"), alias="name")],
            filters=[
                PlanFilter(reference=field(compiler, hotel, "rooms"), operator="gt", values=["100"])
            ],
        )
        compiled = compiler.compile(filtered)
        rows = SqlExecutor(get_readonly_engine(), 5000, 200).execute(
            compiled.validated, compiled.parameters
        )
        assert (
            sorted(r["name"] for r in rows) == expected
            and "JOIN" not in compiled.validated.statement
        )
    finally:
        repo.delete(dataset.dataset_id, delete_conversations=True)
