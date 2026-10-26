"""Five domains traverse router, approved JOIN, real TEMP SQL and grounded composition."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.database.guest_access import configure_guest_access
from app.database.session import get_setup_engine
from app.datasets.relationships import RelationshipInput, RelationshipRecord, verify_relationship
from app.guest.pipeline import GuestSqlDatabase, run_guest_chat
from app.guest.worker import parse_guest_file
from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.query_plan import PlanDecision
from tests.hybrid_fixtures import explanation_draft
from tests.plan_fixtures import decision_from_sql
from tests.test_guest_integration import OfflineEmbedder

pytestmark = pytest.mark.integration

DOMAINS = [
    ("products", "transactions"),
    ("students", "payments"),
    ("departments", "employees"),
    ("routes", "shipments"),
    ("meters", "readings"),
]


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("route", [RouteLabel.SQL, RouteLabel.HYBRID])
def test_domain_pipeline_matches_independent_fact_grain_oracle(
    domain: tuple[str, str],
    model: str,
    route: RouteLabel,
) -> None:
    configure_guest_access(get_setup_engine())
    settings = get_settings().model_copy(
        update={"sql_join_v1_enabled": True, "ai_default_model": model}
    )
    files = [
        parse_guest_file(domain[0] + ".csv", b"Id,Name\n101,A\n102,B\n103,C\n", None, settings),
        parse_guest_file(
            domain[1] + ".csv", b"Key,Amount\n101,20.25\n101,0.00\n102,\n103,0.00\n", None, settings
        ),
        parse_guest_file(
            "rules.md",
            b"# Synthetic\n\nThreshold 40. NULL is unknown, zero is measured.",
            None,
            settings,
        ),
    ]
    request = RelationshipInput(
        source_table_id=files[1].file_id,
        source_column="key",
        target_table_id=files[0].file_id,
        target_column="id",
    )
    database = GuestSqlDatabase(settings, files)
    try:
        with database.engine.connect() as connection:
            preview = verify_relationship(connection, request, database.file_tables)
            # The oracle groups only facts, independently of the JOIN emitted by the gateway.
            oracle = {
                row.key: (row.total, row.average, row.n)
                for row in connection.execute(
                    text(
                        "SELECT key, SUM(amount) AS total, AVG(amount) AS average, COUNT(*) AS n "
                        "FROM pg_temp.table_2 GROUP BY key"
                    )
                )
            }
    finally:
        database.close()
    assert preview.valid
    record = RelationshipRecord(**preview.model_dump(), relationship_id="synthetic-confirmed")
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            if schema is RouteDecision:
                assert domain[0] + ".csv" in prompt and domain[1] + ".csv" in prompt
                return RouteDecision(route=route, reason="Offline capability contract")
            if schema is PlanDecision:
                assert '"source": "t1.c' in prompt and '"target": "t0.c' in prompt
                return decision_from_sql(
                    "SELECT d.id, d.name, SUM(f.amount) AS total, AVG(f.amount) AS average, "
                    "COUNT(*) AS fact_row_count FROM pg_temp.table_2 f "
                    "INNER JOIN pg_temp.table_1 d ON f.key=d.id "
                    "WHERE d.id>=101 GROUP BY d.id,d.name ORDER BY d.id",
                    prompt,
                )
            if schema is HybridAnswerDraft:
                assert "Threshold 40" in prompt and '"total": null' in prompt
                return explanation_draft(prompt, [1])
            raise AssertionError(schema)

        def generate_text(self, prompt):
            calls.append("answer")
            assert '"total": "20.25"' in prompt and '"total": "0.00"' in prompt
            return "A=20.25; B=NULL; C=0.00"

    with patch("app.ai.chat.build_generation_gateway", return_value=Gateway()):
        result = run_guest_chat(
            files,
            "Tổng và trung bình theo danh mục, đối chiếu quy định?",
            settings,
            embedder=OfflineEmbedder(),
            relationships=(record,),
        )
    assert result.route == route and result.used_model == model
    assert [row["id"] for row in result.rows] == [101, 102, 103]
    for row in result.rows:
        expected_sum, expected_avg, expected_count = oracle[row["id"]]
        assert row["fact_row_count"] == expected_count
        assert (None if row["total"] is None else Decimal(row["total"])) == expected_sum
        assert (None if row["average"] is None else Decimal(row["average"])) == expected_avg
    assert result.rows[1]["total"] is None
    assert result.rows[2]["total"] == "0.00"
    assert len(calls) == (2 if route == RouteLabel.SQL else 3)
    assert bool(result.sources) is (route == RouteLabel.HYBRID)
    if result.sources:
        assert result.sources[0].source_file == "rules.md"


@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("metric", ["average", "orders"])
def test_single_table_questions_need_no_relationship(model: str, metric: str) -> None:
    configure_guest_access(get_setup_engine())
    settings = get_settings().model_copy(
        update={"sql_join_v1_enabled": False, "ai_default_model": model}
    )
    if metric == "average":
        question = "Cho tôi biết giá trung bình của từng sản phẩm trong kho."
        data = b"Product,Price\nPen,10.25\nPen,0.00\nBook,20.50\nBook,\n"
        sql = (
            "SELECT product, AVG(price) AS average FROM pg_temp.table_1 "
            "GROUP BY product ORDER BY product"
        )
        expected = [
            {"product": "Book", "average": "20.5000000000000000"},
            {"product": "Pen", "average": "5.1250000000000000"},
        ]
    else:
        question = "Tổng số đơn hàng là bao nhiêu?"
        data = b"Order id,Amount\n1001,10.25\n1002,0.00\n1003,\n"
        sql = "SELECT COUNT(*) AS order_count FROM pg_temp.table_1"
        expected = [{"order_count": 3}]
    files = [parse_guest_file(metric + ".csv", data, None, settings)]
    database = GuestSqlDatabase(settings, files)
    try:
        with database.engine.connect() as connection:
            if metric == "orders":
                oracle = connection.scalar(text("SELECT COUNT(order_id) FROM pg_temp.table_1"))
                assert oracle == 3
            else:
                oracle = connection.execute(
                    text(
                        "SELECT product, SUM(price)/COUNT(price) FROM pg_temp.table_1 "
                        "GROUP BY product ORDER BY product"
                    )
                ).all()
                assert oracle == [("Book", Decimal("20.50")), ("Pen", Decimal("5.125"))]
    finally:
        database.close()

    class Gateway:
        def generate_structured(self, prompt, schema):
            if schema is RouteDecision:
                assert question in prompt
                assert "Never JOIN tables" not in prompt
                return RouteDecision(route=RouteLabel.SQL, reason="Single table fixture")
            assert schema is PlanDecision
            assert '"relationships": []' in prompt
            return decision_from_sql(sql, prompt)

        def generate_text(self, prompt):
            return "Synthetic rows only"

    with patch("app.ai.chat.build_generation_gateway", return_value=Gateway()):
        result = run_guest_chat(files, question, settings, embedder=OfflineEmbedder())
    assert result.route == RouteLabel.SQL and result.used_model == model
    assert result.rows == expected
    assert "JOIN" not in result.sql and not result.sources
