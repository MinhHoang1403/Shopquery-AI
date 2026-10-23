from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Numeric, and_, bindparam, cast, func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import SqlValidationError
from app.datasets.repository import SQL_TYPES
from app.text_to_sql.query_plan import PlanExpression
from app.text_to_sql.schema_context import BUSINESS_TIME_ZONE

NUMERIC = {"BIGINT", "NUMERIC"}
TEMPORAL = {"DATE", "TIMESTAMP", "TIMESTAMPTZ"}


@dataclass(frozen=True)
class ExpressionBinding:
    sql: ColumnElement
    kind: str
    aggregate: bool = False
    ungrouped: frozenset[str] = frozenset()
    constant: Any = None
    temporal_transform: bool = False


class ExpressionCompiler:
    def __init__(
        self,
        nodes: list[PlanExpression],
        column: Callable[[str], ColumnElement],
        column_kind: Callable[[str], str],
        parse_value: Callable[[str, str], Any],
    ) -> None:
        self._nodes = nodes
        self._column = column
        self._column_kind = column_kind
        self._parse_value = parse_value
        self._bindings: dict[str, ExpressionBinding] = {}
        for index, node in enumerate(nodes):
            self._bindings[f"e{index}"] = self._compile(node, index)

    def resolve(self, reference: str) -> ExpressionBinding:
        if reference in self._bindings:
            return self._bindings[reference]
        return ExpressionBinding(
            self._column(reference), self._column_kind(reference), ungrouped=frozenset({reference})
        )

    def _compile(self, node: PlanExpression, index: int) -> ExpressionBinding:
        op = node.operation
        if op == "literal":
            if node.arguments or node.value is None or node.value_type is None:
                raise SqlValidationError("Literal requires one typed value")
            value = self._parse_value(node.value, node.value_type)
            return ExpressionBinding(
                bindparam(f"literal_{index}", value, type_=SQL_TYPES[node.value_type]()),
                node.value_type,
                constant=value,
            )
        if node.value is not None or node.value_type is not None:
            raise SqlValidationError("Only literals take values")
        args = [self.resolve(ref) for ref in node.arguments]
        unary = {
            "sum",
            "avg",
            "min",
            "max",
            "value_count",
            "is_null",
            "is_not_null",
            "day",
            "month",
            "year",
            "month_label",
            "date_label",
        }
        if op == "row_count":
            if args:
                raise SqlValidationError("Row count takes no arguments")
            return ExpressionBinding(func.count(), "BIGINT", True)
        if (
            op in unary
            and len(args) != 1
            or op not in unary | {"and", "or", "in"}
            and len(args) != 2
            or op in {"and", "or", "in"}
            and len(args) < 2
        ):
            raise SqlValidationError("Expression arity is invalid")
        aggregate = any(arg.aggregate for arg in args)
        ungrouped = frozenset().union(*(arg.ungrouped for arg in args))
        if op in {"sum", "avg", "min", "max", "value_count"}:
            arg = args[0]
            if aggregate or arg.kind == "BOOLEAN" and op != "value_count":
                raise SqlValidationError("Invalid aggregate argument or nested aggregate")
            if op in {"sum", "avg"} and arg.kind not in NUMERIC:
                raise SqlValidationError("Numeric aggregate requires numeric values")
            if op == "value_count" and node.arguments[0].startswith("e"):
                raise SqlValidationError("Value count requires a direct source column")
            function = {
                "sum": func.sum,
                "avg": func.avg,
                "min": func.min,
                "max": func.max,
                "value_count": func.count,
            }[op]
            kind = (
                "BIGINT" if op == "value_count" else "NUMERIC" if op in {"sum", "avg"} else arg.kind
            )
            return ExpressionBinding(function(arg.sql), kind, True)
        if op in {"add", "subtract", "multiply", "divide"}:
            if any(arg.kind not in NUMERIC for arg in args):
                raise SqlValidationError("Arithmetic requires numeric arguments")
            left, right = (arg.sql for arg in args)
            if op == "divide":
                if args[1].constant == 0:
                    raise SqlValidationError("Literal division by zero")
                # SUM(x)/COUNT(x) is AVG(x), including empty/all-NULL groups. No derived
                # COUNT is exposed as a row metric; the existing COUNT contract stays intact.
                numerator, denominator = (
                    self._nodes[int(ref[1:])] if ref.startswith("e") else None
                    for ref in node.arguments
                )
                if (
                    numerator
                    and denominator
                    and numerator.operation == "sum"
                    and denominator.operation == "value_count"
                    and numerator.arguments == denominator.arguments
                ):
                    result = func.avg(self.resolve(numerator.arguments[0]).sql)
                else:
                    result = cast(left, Numeric()) / func.nullif(right, 0)
            else:
                result = {
                    "add": lambda: left + right,
                    "subtract": lambda: left - right,
                    "multiply": lambda: left * right,
                }[op]()
            return ExpressionBinding(result, "NUMERIC", aggregate, ungrouped)
        if op in {"and", "or"}:
            if any(arg.kind != "BOOLEAN" for arg in args):
                raise SqlValidationError("Boolean combination requires predicates")
            sql = (and_ if op == "and" else or_)(*(arg.sql for arg in args))
        elif op in {"is_null", "is_not_null"}:
            sql = args[0].sql.is_(None) if op == "is_null" else args[0].sql.is_not(None)
        elif op in {"eq", "ne", "gt", "gte", "lt", "lte", "in"}:
            kinds = {arg.kind for arg in args}
            if len(kinds) != 1 and not kinds <= NUMERIC:
                raise SqlValidationError("Comparison types do not match")
            left = args[0].sql
            if op == "in":
                if any(arg.constant is None for arg in args[1:]):
                    raise SqlValidationError("IN requires bounded literal values")
                sql = left.in_([arg.sql for arg in args[1:]])
            else:
                right = args[1].sql
                sql = {
                    "eq": lambda: left == right,
                    "ne": lambda: left != right,
                    "gt": lambda: left > right,
                    "gte": lambda: left >= right,
                    "lt": lambda: left < right,
                    "lte": lambda: left <= right,
                }[op]()
        else:
            arg = args[0]
            if arg.kind not in TEMPORAL or aggregate:
                raise SqlValidationError("Date grouping requires a source temporal expression")
            value = (
                arg.sql.op("AT TIME ZONE")(BUSINESS_TIME_ZONE)
                if arg.kind == "TIMESTAMPTZ"
                else arg.sql
            )
            if op in {"month_label", "date_label"}:
                return ExpressionBinding(
                    func.to_char(value, "YYYY-MM" if op == "month_label" else "YYYY-MM-DD"),
                    "TEXT",
                    ungrouped=ungrouped,
                    temporal_transform=True,
                )
            return ExpressionBinding(
                func.date_trunc(op, value),
                "TIMESTAMP",
                ungrouped=ungrouped,
                temporal_transform=True,
            )
        return ExpressionBinding(
            sql,
            "BOOLEAN",
            aggregate,
            ungrouped,
            temporal_transform=any(arg.temporal_transform for arg in args),
        )
