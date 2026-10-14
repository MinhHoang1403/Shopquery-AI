"""The compact schema and business context supplied to SQL generation."""

SCHEMA_CONTEXT = """
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
- Interpret calendar dates in Asia/Ho_Chi_Minh and use half-open [start, end) filters.
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
