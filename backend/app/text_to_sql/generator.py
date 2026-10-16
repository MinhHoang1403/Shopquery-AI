"""Structured Gemini SQL generation."""

from pydantic import BaseModel, Field

from app.ai.gemini import GenerationGateway
from app.text_to_sql.schema_context import SCHEMA_CONTEXT


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
Do not add date, status, category, or other filters unless the question requests them.
For scalar SUM or AVG questions where missing matches matter, also select a separate COUNT(*)
AS matched_row_count so a null aggregate can be distinguished from zero and from all-null
values. Never label a SUM, AVG, or requested business metric as matched_row_count.
Select every column needed to answer every part of the question. For category-based policy or
eligibility comparisons, join categories and include category_code and category_name. Never
infer a category from product_name.

{self._schema_context}

The reproducible reference date for relative expressions is {self._reference_date}.
Question: {question}
""".strip()
        return self._gateway.generate_structured(prompt, SqlDraft).sql.strip()
