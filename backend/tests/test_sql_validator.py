"""Representative queries and hostile SQL validation cases."""

import pytest

from app.core.errors import SqlValidationError
from app.text_to_sql.validator import SqlValidator

VALID_QUERIES = [
    """
    SELECT p.product_id, p.product_name, SUM(oi.quantity) AS total_quantity
    FROM products AS p
    JOIN order_items AS oi ON oi.product_id = p.product_id
    JOIN orders AS o ON o.order_id = oi.order_id
    WHERE o.status = 'completed'
      AND o.order_date >= TIMESTAMPTZ '2025-09-01 00:00:00+07'
      AND o.order_date < TIMESTAMPTZ '2025-10-01 00:00:00+07'
    GROUP BY p.product_id, p.product_name
    ORDER BY total_quantity DESC
    LIMIT 5
    """,
    """
    SELECT SUM(oi.quantity * oi.unit_price) AS revenue
    FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
    WHERE o.status = 'completed'
    """,
    """
    SELECT c.category_code, SUM(oi.quantity * oi.unit_price) AS revenue
    FROM categories c JOIN products p ON p.category_id = c.category_id
    JOIN order_items oi ON oi.product_id = p.product_id
    JOIN orders o ON o.order_id = oi.order_id
    WHERE o.status = 'completed'
    GROUP BY c.category_code ORDER BY revenue DESC LIMIT 1
    """,
    "SELECT COUNT(*) AS completed_orders FROM orders WHERE status = 'completed'",
    """
    SELECT DATE_TRUNC('month', o.order_date) AS sales_month,
           SUM(oi.quantity * oi.unit_price) AS revenue
    FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY DATE_TRUNC('month', o.order_date)
    ORDER BY sales_month
    """,
]


@pytest.mark.parametrize("sql", VALID_QUERIES)
def test_accepts_representative_selects(sql: str) -> None:
    validated = SqlValidator().validate(sql)
    assert validated.statement.startswith("SELECT")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "DROP TABLE products",
        "UPDATE products SET price = 0",
        "SELECT COUNT(*) FROM orders; SELECT COUNT(*) FROM products",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM (SELECT * FROM orders) nested",
        "WITH changed AS (DELETE FROM orders RETURNING *) SELECT * FROM changed",
        "SELECT pg_sleep(1) FROM orders",
        "SELECT missing_column FROM products",
    ],
)
def test_rejects_unsafe_or_out_of_scope_sql(sql: str) -> None:
    with pytest.raises(SqlValidationError):
        SqlValidator().validate(sql)
