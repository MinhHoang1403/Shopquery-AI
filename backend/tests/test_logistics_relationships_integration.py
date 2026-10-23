"""Numbered Vietnamese uploads must produce trusted keys before SQL generation."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.database.session import get_setup_engine
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.query_plan import PlanDecision
from tests.plan_fixtures import decision_from_sql
from tests.test_auth_integration import accounts  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("model", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("three_tables", [False, True])
@pytest.mark.parametrize("reverse_upload", [False, True])
def test_numbered_logistics_upload_sql_owner_csrf_and_history(
    accounts,  # noqa: F811
    monkeypatch,
    model,
    three_tables,
    reverse_upload,
):
    a, b = accounts.a, accounts.b
    accounts.settings.sql_join_v1_enabled = True
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: accounts.settings)
    dataset = a.datasets.create_workspace("Logistics synthetic " + uuid4().hex)
    path = f"/api/datasets/{dataset.dataset_id}"
    files = [
        ("01_kho_dieu_phoi.csv", b"kho_id,ten_kho\nK1,North\nK2,South\n"),
        ("02_tai_xe.csv", b"tai_xe_id,ten_tai_xe,kho_id\nD1,An,K1\nD2,Binh,K1\nD3,Chi,K2\n"),
        (
            "03_don_giao_hang.csv",
            b"don_id,tai_xe_id,phi_giao_vnd\nO1,D1,20.00\n"
            b"O2,D1,0.00\nO3,D2,\nO4,D3,12.50\nO5,D3,0.00\n",
        ),
    ]
    for name, content in reversed(files) if reverse_upload else files:
        assert (
            a.client.post(
                path + "/tables/import",
                files={"file": (name, content)},
                headers={"X-CSRF-Token": "bad"},
            ).status_code
            == 403
        )
        assert (
            b.client.post(
                path + "/tables/import",
                files={"file": (name, content)},
            ).status_code
            == 404
        )
        result = a.client.post(path + "/tables/import", files={"file": (name, content)})
        assert result.status_code == 201, result.text
    relations = a.client.get(path + "/relationships").json()["relationships"]
    assert len(relations) == 1
    assert all(
        r["valid"] and r["origin"] == "automatic" and not r["confirmed"] and r["orphan_rows"] == 0
        for r in relations
    )
    assert b.client.get(path + "/relationships").status_code == 404
    imported = {t.display_name: t for t in a.datasets.get(dataset.dataset_id).tables}
    request = {
        "source_table_id": str(imported["02_tai_xe"].dataset_table_id),
        "source_column": "kho_id",
        "target_table_id": str(imported["01_kho_dieu_phoi"].dataset_table_id),
        "target_column": "kho_id",
    }
    preview = a.client.post(path + "/relationships/preview", json=request).json()
    assert preview["valid"]
    confirmed = a.client.post(
        path + "/relationships",
        json={
            **request,
            "revision": preview["revision"],
            "confirmed": True,
        },
    )
    assert confirmed.status_code == 200 and confirmed.json()["origin"] == "manual"
    assert len(a.client.get(path + "/relationships").json()["relationships"]) == 2
    tables = {
        t.display_name: t.physical_table_name for t in a.datasets.get(dataset.dataset_id).tables
    }
    k, d, f = (tables[n] for n in ("01_kho_dieu_phoi", "02_tai_xe", "03_don_giao_hang"))
    attribute, key = ("k.ten_kho", "k.kho_id") if three_tables else ("d.ten_tai_xe", "d.tai_xe_id")
    sql = (
        f"SELECT {attribute} AS name, SUM(f.phi_giao_vnd) AS total, "
        f"COUNT(*) AS fact_row_count FROM uploaded_data.{f} f "
        f"INNER JOIN uploaded_data.{d} d ON f.tai_xe_id=d.tai_xe_id "
        + (f"INNER JOIN uploaded_data.{k} k ON d.kho_id=k.kho_id " if three_tables else "")
        + f"GROUP BY {key},{attribute} ORDER BY {attribute}"
    )
    with get_setup_engine().connect() as connection:
        group = (
            "CASE WHEN tai_xe_id IN ('D1','D2') THEN 'North' ELSE 'South' END"
            if three_tables
            else ("CASE tai_xe_id WHEN 'D1' THEN 'An' WHEN 'D2' THEN 'Binh' ELSE 'Chi' END")
        )
        oracle = (
            connection.execute(
                text(
                    f"SELECT {group} AS name, SUM(phi_giao_vnd)::text AS total, "
                    f"COUNT(*) AS fact_row_count FROM uploaded_data.{f} GROUP BY 1 ORDER BY 1"
                )
            )
            .mappings()
            .all()
        )
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            assert "No approved table-to-table relationships" not in prompt
            assert "Safe three-table tree" in prompt or '"relationships": [' in prompt
            if schema is RouteDecision:
                return RouteDecision(route=RouteLabel.SQL, reason="Offline synthetic logistics")
            assert schema is PlanDecision and "Row count has zero arguments" in prompt
            return decision_from_sql(sql, prompt)

        def generate_text(self, prompt):
            calls.append("answer")
            assert '"total": "20.00"' in prompt and '"total": "12.50"' in prompt
            return "Synthetic logistics result"

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    conversation = a.chats.create(dataset.dataset_id, model)
    chat_path = f"/api/conversations/{conversation.conversation_id}"
    result = a.client.post(
        chat_path + "/messages",
        json={
            "message": "Tên kho, số đơn và tổng phí"
            if three_tables
            else "Tên tài xế, số đơn và tổng phí",
            "model_id": model,
        },
    )
    assert result.status_code == 200, result.text
    response = result.json()["assistant_message"]["response"]
    assert response["route"] == "SQL" and response["error"] is None
    assert response["used_model"] == model and not response["fallback_used"]
    assert response["sql"].count("JOIN") == (2 if three_tables else 1)
    assert response["rows"] == [dict(r) for r in oracle]
    assert calls == ["RouteDecision", "PlanDecision", "answer"]
    assert a.client.get(chat_path).json()["messages"][-1]["response"] == response
    assert b.client.get(chat_path).status_code == 404
