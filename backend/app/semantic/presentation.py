"""Typed output selection after full policy verification; never changes SQL population."""

from datetime import date, datetime
from decimal import Decimal
from functools import cmp_to_key

from app.routing.hybrid_policy_binding import verification_error
from app.semantic.task import OutputSelection
from app.text_to_sql.answer import ResultColumn


def select_verified_rows(
    output: OutputSelection,
    rows: list[dict],
    statuses: list[str],
    columns: tuple[ResultColumn, ...],
) -> tuple[int, ...]:
    if len(rows) != len(statuses) or output.predicates is not None:
        raise verification_error("planning_scope_violation")
    indices = [
        i
        for i, status in enumerate(statuses)
        if output.classification == "all" or status == output.classification
    ]
    metadata = {column.key: column for column in columns}
    aliases = {field.reference: field.alias for field in output.fields}

    def value(index: int, key: str):
        if key not in rows[index] or key not in metadata:
            raise verification_error("planning_scope_violation")
        raw = rows[index][key]
        if raw is None:
            return None
        kind = metadata[key].data_type
        try:
            if kind in {"NUMERIC", "BIGINT"}:
                if isinstance(raw, (float, bool)):
                    raise ValueError("Binary floats and booleans are not exact SQL numerics")
                number = Decimal(str(raw))
                if not number.is_finite():
                    raise ValueError("Non-finite output")
                return number
            if kind == "DATE":
                return date.fromisoformat(str(raw))
            if kind in {"TIMESTAMP", "TIMESTAMPTZ"}:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if kind == "TEXT" and isinstance(raw, str):
                return raw
            if kind == "BOOLEAN" and isinstance(raw, bool):
                return raw
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise verification_error("planning_scope_violation") from exc
        raise verification_error("planning_scope_violation")

    def compare(left: int, right: int) -> int:
        for order in output.ordering:
            key = aliases.get(order.field, order.field)
            a, b = value(left, key), value(right, key)
            if a is None or b is None:
                result = 0 if a is b else (-1 if a is None else 1)
                if order.nulls == "last":
                    result = -result
            else:
                try:
                    result = (a > b) - (a < b)
                except TypeError as exc:
                    raise verification_error("planning_scope_violation") from exc
                if order.direction == "desc":
                    result = -result
            if result:
                return result
        return 0

    # Validate every requested sort key even when the selected set has 0/1 rows.
    for order in output.ordering:
        key = aliases.get(order.field, order.field)
        if key not in metadata:
            raise verification_error("planning_scope_violation")
        for index in indices:
            value(index, key)
    return tuple(sorted(indices, key=cmp_to_key(compare))[: output.limit])
