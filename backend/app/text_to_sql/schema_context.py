"""The compact schema and business context supplied to SQL generation."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.datasets.context import DatasetSqlContext

BUSINESS_TIME_ZONE = "Asia/Ho_Chi_Minh"

SCHEMA_CONTEXT = f"""
PostgreSQL schema:
- categories(category_id INTEGER PK, category_code VARCHAR UNIQUE NOT NULL,
  category_name VARCHAR NOT NULL)
- products(product_id INTEGER PK, category_id INTEGER FK -> categories.category_id,
  sku VARCHAR UNIQUE, product_name VARCHAR, price NUMERIC(14,0), is_active BOOLEAN)
- orders(order_id INTEGER PK, order_date TIMESTAMPTZ, status VARCHAR)
- order_items(order_item_id INTEGER PK, order_id INTEGER FK -> orders.order_id,
  product_id INTEGER FK -> products.product_id, quantity INTEGER,
  unit_price NUMERIC(14,0))

Relationships:
categories 1--N products; products 1--N order_items; orders 1--N order_items.

Business rules:
- Revenue = SUM(order_items.quantity * order_items.unit_price), using only orders whose
  status is 'completed'. Never use products.price for historical revenue.
- Best-selling means SUM(order_items.quantity) from completed orders unless the question
  explicitly asks for another definition.
- Distinguish top products by quantity from top products by revenue.
- Interpret calendar dates in {BUSINESS_TIME_ZONE} and use half-open [start, end) filters.

Default-store SQL rules (apply only to this schema):
- Use explicit joins along the declared relationships.
- For category-based policy comparisons, join categories;
  include category_code and category_name. Never infer a category from product_name.
- category_code belongs only to categories, joined through products.category_id.
  The orders table has only order_id, order_date and status; it has no category columns.
- For shipping or warranty questions, always select BOTH categories.category_code and
  categories.category_name along with each product; include both in GROUP BY when aggregating.
  Policy documents use the codes; the category name alone is insufficient evidence.
""".strip()

TABLE_COLUMNS: dict[str, set[str]] = {
    "categories": {"category_id", "category_code", "category_name"},
    "products": {
        "product_id",
        "category_id",
        "sku",
        "product_name",
        "price",
        "is_active",
    },
    "orders": {"order_id", "order_date", "status"},
    "order_items": {
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
    },
}


def default_sql_context() -> "DatasetSqlContext":
    """Only the four public demo models and their declared foreign keys are exposed."""
    from sqlalchemy import Boolean, DateTime, Integer, Numeric

    from app.database.models import Category, Order, OrderItem, Product
    from app.datasets.context import DatasetSqlContext
    from app.text_to_sql.join_policy import ApprovedJoin

    models = (Category, Product, Order, OrderItem)
    types = {}
    joins = []
    for model in models:
        table = model.__table__
        types[table.name] = {}
        for column in table.columns:
            kind = column.type
            types[table.name][column.name] = (
                "BOOLEAN"
                if isinstance(kind, Boolean)
                else "BIGINT"
                if isinstance(kind, Integer)
                else "NUMERIC"
                if isinstance(kind, Numeric)
                else "TIMESTAMPTZ"
                if isinstance(kind, DateTime) and kind.timezone
                else "TEXT"
            )
            for foreign_key in column.foreign_keys:
                target = foreign_key.column
                joins.append(
                    ApprovedJoin(
                        f"{table.name}.{column.name}",
                        table.name,
                        column.name,
                        target.table.name,
                        target.name,
                        "declared-demo-schema",
                    )
                )
    return DatasetSqlContext(
        schema_context=SCHEMA_CONTEXT,
        table_columns=TABLE_COLUMNS,
        allowed_schemas={},
        column_types=types,
        approved_joins=tuple(joins),
    )
