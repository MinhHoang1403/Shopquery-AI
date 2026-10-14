"""Validated and repeatable CSV loading for commerce tables."""

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, delete, insert

from app.database.models import Category, Order, OrderItem, Product


def _read_csv(directory: Path, filename: str) -> list[dict[str, str]]:
    path = directory / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing seed file: {path}")
    with path.open(encoding="utf-8", newline="") as file_handle:
        return list(csv.DictReader(file_handle))


def load_seed_csv(engine: Engine, directory: Path) -> dict[str, int]:
    """Replace commerce seed rows atomically so reruns cannot create duplicates."""

    categories = [
        {
            "category_id": int(row["category_id"]),
            "category_code": row["category_code"],
            "category_name": row["category_name"],
        }
        for row in _read_csv(directory, "categories.csv")
    ]
    products = [
        {
            "product_id": int(row["product_id"]),
            "category_id": int(row["category_id"]),
            "sku": row["sku"],
            "product_name": row["product_name"],
            "price": Decimal(row["price"]),
            "is_active": row["is_active"].lower() == "true",
        }
        for row in _read_csv(directory, "products.csv")
    ]
    orders = [
        {
            "order_id": int(row["order_id"]),
            "order_date": datetime.fromisoformat(row["order_date"]),
            "status": row["status"],
        }
        for row in _read_csv(directory, "orders.csv")
    ]
    order_items = [
        {
            "order_item_id": int(row["order_item_id"]),
            "order_id": int(row["order_id"]),
            "product_id": int(row["product_id"]),
            "quantity": int(row["quantity"]),
            "unit_price": Decimal(row["unit_price"]),
        }
        for row in _read_csv(directory, "order_items.csv")
    ]

    if (len(categories), len(products), len(orders)) != (8, 150, 2_000):
        raise ValueError("Seed CSV counts do not match the required dataset")

    with engine.begin() as connection:
        connection.execute(delete(OrderItem))
        connection.execute(delete(Order))
        connection.execute(delete(Product))
        connection.execute(delete(Category))
        connection.execute(insert(Category), categories)
        connection.execute(insert(Product), products)
        connection.execute(insert(Order), orders)
        connection.execute(insert(OrderItem), order_items)

    return {
        "categories": len(categories),
        "products": len(products),
        "orders": len(orders),
        "order_items": len(order_items),
    }
