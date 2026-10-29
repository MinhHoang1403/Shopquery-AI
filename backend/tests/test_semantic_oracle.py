"""Independent arithmetic check of the frozen gold; not PostgreSQL acceptance."""

import json
from decimal import Decimal
from pathlib import Path


def test_execution_gold_has_independent_exact_arithmetic_and_null_semantics():
    gold = json.loads(
        Path(__file__)
        .with_name("fixtures")
        .joinpath("semantic_execution_oracle.json")
        .read_text(encoding="utf-8")
    )
    rows = [dict(zip(gold["columns"], row, strict=True)) for row in gold["events"]]

    def totals(selected):
        values = [Decimal(row["amount"]) for row in selected if row["amount"] is not None]
        return {
            "row_count": len(selected),
            "value_count": len(values),
            "total": str(sum(values, Decimal("0.00"))) if values else None,
        }

    assert totals(rows) == gold["cases"][0]["expected"][0]
    north = [
        row
        for row in rows
        if row["region"] == "North" and "2032-09-01" <= row["event_date"] < "2032-10-01"
    ]
    assert [
        {"entity_id": key, **totals([r for r in north if r["entity_id"] == key])}
        for key in sorted({r["entity_id"] for r in north})
    ] == gold["cases"][1]["expected"]
    actual = {}
    threshold = Decimal(gold["policy"]["threshold"])
    for entity in gold["entity_universe"]:
        total = totals([r for r in rows if r["entity_id"] == entity])["total"]
        actual[entity] = (
            "insufficient_evidence"
            if total is None
            else ("qualified" if Decimal(total) >= threshold else "not_qualified")
        )
    assert actual == gold["expected_policy_status"]
