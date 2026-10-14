"""Offline validation for deterministic commerce data."""

from decimal import Decimal

from app.database.seed_data import calculate_completed_revenue, generate_seed_data


def test_seed_data_is_reproducible_and_consistent() -> None:
    first = generate_seed_data()
    second = generate_seed_data()

    assert first == second
    assert len(first.categories) == 8
    assert len(first.products) == 150
    assert len(first.orders) == 2_000
    assert 2_000 <= len(first.order_items) <= 6_000
    assert calculate_completed_revenue(first) == Decimal("151687001000")


def test_seed_data_covers_each_required_month() -> None:
    data = generate_seed_data()
    covered = {
        (row["order_date"].year, row["order_date"].month) for row in data.orders
    }
    expected = {(2025, month) for month in range(1, 13)} | {
        (2026, month) for month in range(1, 10)
    }
    assert expected <= covered


def test_every_order_has_one_to_three_positive_items() -> None:
    data = generate_seed_data()
    counts: dict[int, int] = {}
    for item in data.order_items:
        order_id = int(item["order_id"])
        counts[order_id] = counts.get(order_id, 0) + 1
        assert int(item["quantity"]) > 0
        assert Decimal(item["unit_price"]) >= 0
    assert set(counts) == set(range(1, 2_001))
    assert all(1 <= count <= 3 for count in counts.values())
