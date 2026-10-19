"""Structured SQL generation using the selected provider."""

from pydantic import BaseModel, Field

from app.ai.gemini import GenerationGateway
from app.text_to_sql.schema_context import BUSINESS_TIME_ZONE, SCHEMA_CONTEXT


class SqlDraft(BaseModel):
    sql: str = Field(description="Exactly one PostgreSQL SELECT statement")


class SqlGenerator:
    def __init__(
        self,
        gateway: GenerationGateway,
        reference_date: str,
        schema_context: str = SCHEMA_CONTEXT,
    ) -> None:
        self._gateway = gateway
        self._reference_date = reference_date
        self._schema_context = schema_context

    def generate(self, question: str) -> str:
        prompt = f"""
You generate one read-only PostgreSQL SELECT query for ShopQuery AI.
Return only the structured field requested by the response schema.
Do not use CTEs, subqueries, comments, SELECT INTO, locks, catalog tables, or functions
outside common aggregation and date formatting. Use explicit joins.
Do not use window functions or OVER. Use GROUP BY, ORDER BY and LIMIT for top-N queries.
Do not add date, status, category, or other filters unless the question requests them.
For scalar SUM or AVG questions where missing matches matter, also select a separate COUNT(*)
AS matched_row_count so a null aggregate can be distinguished from zero and from all-null
values. Never label a SUM, AVG, or requested business metric as matched_row_count.
Select every column needed to answer every part of the question. For category-based policy or
eligibility comparisons, join categories and include category_code and category_name. Never
infer a category from product_name.
Validate each qualified column against the schema before returning the query. For the default
store, category_code belongs only to categories, joined through products.category_id.
The orders table has only order_id, order_date and status; it has no category columns.
For default-store shipping or warranty questions, always select BOTH categories.category_code
and categories.category_name along with each product. Include both in GROUP BY when aggregating.
Policy documents use the codes; the category name alone is insufficient evidence for that policy.

The executor evaluates calendar dates in {BUSINESS_TIME_ZONE}, not UTC.
For TIMESTAMPTZ columns, express local calendar boundaries as TIMESTAMPTZ literals with an
explicit +07:00 offset, or TIMESTAMP literals AT TIME ZONE '{BUSINESS_TIME_ZONE}'.
Keep the date column unchanged in range filters and use >= start AND < end.
Never cast an offset-bearing literal to TIMESTAMP without time zone: that discards its offset.
Do not apply AT TIME ZONE to a TIMESTAMPTZ boundary literal to construct a local month boundary.
Use the actual date range requested; these rules do not introduce a default date filter.

{self._schema_context}

The reproducible reference date for relative expressions is {self._reference_date}.
Question: {question}
""".strip()
        return self._gateway.generate_structured(prompt, SqlDraft).sql.strip()
