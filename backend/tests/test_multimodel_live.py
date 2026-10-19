"""Opt-in evaluation on synthetic data in an isolated database, never in default CI."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.repository import AuthRepository, csrf_token
from app.core.config import get_settings
from app.database.session import get_setup_engine
from app.database.setup import create_schema
from app.database.test_safety import require_test_database
from app.main import app

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_AI") != "1",
        reason="Set RUN_LIVE_AI=1 for controlled live evaluation",
    ),
]


@pytest.fixture(autouse=True)
def live_test_session(monkeypatch):
    settings = get_settings()
    require_test_database(settings.database_setup_url)
    if not settings.beta_provider_data_enabled:
        pytest.fail("Explicit BETA_PROVIDER_DATA_ENABLED=true is required for live AI")
    create_schema(get_setup_engine())
    email = f"live-{uuid4().hex}@example.invalid"
    auth = AuthRepository(get_setup_engine())
    owner = auth.identity(uuid4().hex, email, "Isolated live test")
    raw = auth.create_session(owner, 1)
    monkeypatch.setattr(
        "app.auth.dependencies.get_settings",
        lambda: settings.model_copy(update={"auth_invited_emails": [email]}),
    )
    factory = TestClient
    monkeypatch.setattr(
        "tests.test_multimodel_live.TestClient",
        lambda application: factory(
            application,
            cookies={settings.session_cookie_name: raw},
            headers={
                "Origin": settings.app_origin,
                "X-CSRF-Token": csrf_token(raw),
            },
        ),
    )
    yield
    from app.auth.repository import token_hash

    auth.revoke(token_hash(raw))


@pytest.mark.parametrize(
    ("question", "route", "source"),
    [
        ("Có tổng cộng bao nhiêu sản phẩm trong bảng products?", "SQL", None),
        ("Tổng doanh thu của tất cả đơn hàng completed là bao nhiêu?", "SQL", None),
        (
            "Khách hàng có bao nhiêu ngày kể từ khi nhận hàng để yêu cầu đổi trả?",
            "RAG",
            "return_policy.md",
        ),
        ("Những mã danh mục nào được miễn phí vận chuyển tiêu chuẩn?", "RAG", "shipping_policy.md"),
        (
            "Top 5 sản phẩm bán chạy nhất thuộc danh mục nào và có được miễn phí vận chuyển không?",
            "HYBRID",
            "shipping_policy.md",
        ),
        (
            "Top 5 sản phẩm bán chạy nhất có thời hạn bảo hành theo danh mục bao nhiêu tháng?",
            "HYBRID",
            "warranty_policy.md",
        ),
        ("Thời tiết Hà Nội ngày mai ra sao?", "UNSUPPORTED", None),
    ],
)
def test_knowledge_routes_against_synthetic_ground_truth(question, route, source):
    settings = get_settings()
    assert settings.database_setup_url.rsplit("/", 1)[-1] != "shopquery"
    result = (
        TestClient(app)
        .post(
            "/api/chat",
            json={
                "message": question,
                "model_id": "inetcloud-knowledge",
            },
        )
        .json()
    )
    assert result["error"] is None, result["error"]
    assert result["route"] == route
    assert result["requested_model"] == result["used_model"] == "inetcloud-knowledge"
    assert result["fallback_used"] is False
    if route == "SQL":
        expected = 150 if "products" in question else 151_687_001_000
        assert expected in [value for row in result["rows"] for value in row.values()]
        assert result["sources"] == []
    elif route == "UNSUPPORTED":
        assert result["rows"] == result["sources"] == []
        assert result["sql"] is None
    else:
        assert source in {item["source_file"] for item in result["sources"]}
        assert len({item["chunk_id"] for item in result["sources"]}) == len(result["sources"])
        if "bao nhiêu ngày" in question:
            assert "14" in result["answer"]
        if route == "HYBRID":
            with get_setup_engine().connect() as connection:
                expected_rows = (
                    connection.execute(
                        text(
                            "SELECT p.product_name, c.category_code, "
                            "SUM(oi.quantity) AS total_quantity "
                            "FROM order_items oi JOIN orders o ON o.order_id=oi.order_id "
                            "JOIN products p ON p.product_id=oi.product_id "
                            "JOIN categories c ON c.category_id=p.category_id "
                            "WHERE o.status='completed' GROUP BY p.product_name,c.category_code "
                            "ORDER BY total_quantity DESC"
                        )
                    )
                    .mappings()
                    .all()
                )
            assert len(result["rows"]) == 5
            eligible_names = {
                row["product_name"]
                for row in expected_rows
                if row["total_quantity"] >= expected_rows[4]["total_quantity"]
            }
            assert {row["product_name"] for row in result["rows"]} <= eligible_names
            required_names = {
                row["product_name"]
                for row in expected_rows
                if row["total_quantity"] > expected_rows[4]["total_quantity"]
            }
            assert required_names <= {row["product_name"] for row in result["rows"]}
            assert all("category_code" in row for row in result["rows"])
            assert all(
                row["product_name"] in result["answer"]
                or row["category_code"] in result["answer"]
                or row.get("category_name", "__missing__") in result["answer"]
                for row in result["rows"]
            )
            if source == "warranty_policy.md":
                months = {
                    "PHONE": "24",
                    "LAPTOP": "24",
                    "CAMERA": "12",
                    "GAMING": "12",
                    "HOME": "12",
                    "OFFICE": "12",
                    "AUDIO": "6",
                    "ACCESSORY": "6",
                }
                assert all(
                    months[row["category_code"]] in result["answer"] for row in result["rows"]
                )


def test_manual_gemini_remains_available():
    result = (
        TestClient(app)
        .post(
            "/api/chat",
            json={
                "message": "Có tổng cộng bao nhiêu sản phẩm trong bảng products?",
                "model_id": "gemini",
            },
        )
        .json()
    )
    assert result["error"] is None, result["error"]
    assert result["route"] == "SQL"
    assert result["requested_model"] == result["used_model"] == "gemini"
    assert not result["fallback_used"]
    assert 150 in [value for row in result["rows"] for value in row.values()]
