"""Deterministic e-commerce seed-data generation and validation."""

import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

CATEGORY_DEFINITIONS = (
    (1, "PHONE", "Điện thoại", 3_000_000, 35_000_000, "Điện thoại"),
    (2, "LAPTOP", "Máy tính xách tay", 10_000_000, 55_000_000, "Laptop"),
    (3, "AUDIO", "Âm thanh", 500_000, 15_000_000, "Thiết bị âm thanh"),
    (4, "ACCESSORY", "Phụ kiện", 100_000, 5_000_000, "Phụ kiện"),
    (5, "CAMERA", "Máy ảnh", 5_000_000, 60_000_000, "Máy ảnh"),
    (6, "GAMING", "Thiết bị chơi game", 500_000, 30_000_000, "Thiết bị gaming"),
    (7, "HOME", "Gia dụng thông minh", 500_000, 25_000_000, "Thiết bị gia dụng"),
    (8, "OFFICE", "Thiết bị văn phòng", 500_000, 20_000_000, "Thiết bị văn phòng"),
)
ALLOWED_STATUSES = {"pending", "completed", "cancelled"}
RANDOM_SEED = 20251013
PRODUCT_COUNT = 150
ORDER_COUNT = 2_000


@dataclass
class SeedData:
    categories: list[dict[str, object]]
    products: list[dict[str, object]]
    orders: list[dict[str, object]]
    order_items: list[dict[str, object]]


def generate_seed_data(seed: int = RANDOM_SEED) -> SeedData:
    """Generate reproducible commerce records without personal information."""

    randomizer = random.Random(seed)
    categories = [
        {"category_id": row[0], "category_code": row[1], "category_name": row[2]}
        for row in CATEGORY_DEFINITIONS
    ]
    products = _generate_products(randomizer)
    orders = _generate_orders(randomizer)
    order_items = _generate_order_items(randomizer, orders, products)
    data = SeedData(categories, products, orders, order_items)
    validate_seed_data(data)
    return data


def _generate_products(randomizer: random.Random) -> list[dict[str, object]]:
    products: list[dict[str, object]] = []
    base_count, remainder = divmod(PRODUCT_COUNT, len(CATEGORY_DEFINITIONS))
    product_id = 1
    for category_index, category in enumerate(CATEGORY_DEFINITIONS):
        count = base_count + (1 if category_index < remainder else 0)
        _, code, _, minimum, maximum, label = category
        for item_number in range(1, count + 1):
            raw_price = randomizer.randrange(minimum, maximum + 1, 50_000)
            products.append(
                {
                    "product_id": product_id,
                    "category_id": category_index + 1,
                    "sku": f"{code}-{item_number:03d}",
                    "product_name": f"{label} SQ {item_number:03d}",
                    "price": raw_price,
                    "is_active": randomizer.random() >= 0.08,
                }
            )
            product_id += 1
    return products


def _generate_orders(randomizer: random.Random) -> list[dict[str, object]]:
    timezone = ZoneInfo("Asia/Ho_Chi_Minh")
    start = datetime(2025, 1, 1, tzinfo=timezone)
    end = datetime(2026, 10, 1, tzinfo=timezone)
    duration_seconds = int((end - start).total_seconds())
    statuses = ("completed", "pending", "cancelled")
    weights = (0.72, 0.18, 0.10)
    orders: list[dict[str, object]] = []

    # Seed one order in every covered month before adding random timestamps.
    month_starts: list[datetime] = []
    cursor = start
    while cursor < end:
        month_starts.append(cursor + timedelta(days=10, hours=10))
        next_month = cursor.month % 12 + 1
        next_year = cursor.year + (1 if cursor.month == 12 else 0)
        cursor = datetime(next_year, next_month, 1, tzinfo=timezone)

    for order_id in range(1, ORDER_COUNT + 1):
        if order_id <= len(month_starts):
            order_date = month_starts[order_id - 1]
        else:
            order_date = start + timedelta(seconds=randomizer.randrange(duration_seconds))
        orders.append(
            {
                "order_id": order_id,
                "order_date": order_date,
                "status": randomizer.choices(statuses, weights=weights, k=1)[0],
            }
        )
    return orders


def _generate_order_items(
    randomizer: random.Random,
    orders: list[dict[str, object]],
    products: list[dict[str, object]],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    product_by_id = {int(product["product_id"]): product for product in products}
    item_id = 1
    for order in orders:
        selected_ids = randomizer.sample(list(product_by_id), randomizer.randint(1, 3))
        for product_id in selected_ids:
            product = product_by_id[product_id]
            price_factor = randomizer.choice((90, 95, 100, 100, 100, 105))
            unit_price = int(product["price"]) * price_factor // 100
            unit_price = max(0, round(unit_price / 1_000) * 1_000)
            items.append(
                {
                    "order_item_id": item_id,
                    "order_id": order["order_id"],
                    "product_id": product_id,
                    "quantity": randomizer.randint(1, 5),
                    "unit_price": unit_price,
                }
            )
            item_id += 1
    return items


def validate_seed_data(data: SeedData) -> None:
    """Reject inconsistent generated data before it reaches CSV or PostgreSQL."""

    if len(data.categories) != 8 or len(data.products) != PRODUCT_COUNT:
        raise ValueError("Unexpected category or product count")
    if len(data.orders) != ORDER_COUNT:
        raise ValueError("Unexpected order count")
    category_ids = {row["category_id"] for row in data.categories}
    product_ids = {row["product_id"] for row in data.products}
    order_ids = {row["order_id"] for row in data.orders}
    if any(row["category_id"] not in category_ids for row in data.products):
        raise ValueError("Product contains an invalid category foreign key")
    if any(row["status"] not in ALLOWED_STATUSES for row in data.orders):
        raise ValueError("Order contains an invalid status")
    if any(Decimal(row["price"]) < 0 for row in data.products):
        raise ValueError("Product contains a negative price")
    if any(
        row["order_id"] not in order_ids
        or row["product_id"] not in product_ids
        or int(row["quantity"]) <= 0
        or Decimal(row["unit_price"]) < 0
        for row in data.order_items
    ):
        raise ValueError("Order item violates a foreign key, quantity, or price rule")
    populated_orders = {row["order_id"] for row in data.order_items}
    if populated_orders != order_ids:
        raise ValueError("At least one order has no items")


def calculate_completed_revenue(data: SeedData) -> Decimal:
    """Calculate reproducible revenue using completed orders and snapshot prices."""

    completed_ids = {
        row["order_id"] for row in data.orders if row["status"] == "completed"
    }
    return sum(
        (
            Decimal(item["quantity"]) * Decimal(item["unit_price"])
            for item in data.order_items
            if item["order_id"] in completed_ids
        ),
        start=Decimal(0),
    )


def write_seed_csv(data: SeedData, output_directory: Path) -> None:
    """Write the four requested UTF-8 CSV files."""

    output_directory.mkdir(parents=True, exist_ok=True)
    datasets = {
        "categories.csv": data.categories,
        "products.csv": data.products,
        "orders.csv": data.orders,
        "order_items.csv": data.order_items,
    }
    for filename, rows in datasets.items():
        if not rows:
            raise ValueError(f"Cannot write empty dataset: {filename}")
        path = output_directory / filename
        with path.open("w", encoding="utf-8", newline="") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                serialized = {
                    key: value.isoformat() if isinstance(value, datetime) else value
                    for key, value in row.items()
                }
                writer.writerow(serialized)
