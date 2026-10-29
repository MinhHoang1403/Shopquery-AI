from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from operator import eq, ge, gt, le, lt, ne
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Column, MetaData, Table, and_, bindparam, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import BindTyping
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.functions import FunctionElement
from sqlglot import exp, parse_one

from app.core.errors import (
    ErrorContext,
    SqlUnsupportedError,
    SqlValidationError,
    validation_context,
)
from app.datasets.context import DatasetSqlContext
from app.datasets.repository import SQL_TYPES
from app.text_to_sql.answer import ResultColumn, column_label
from app.text_to_sql.count_contract import analyze_counts
from app.text_to_sql.expressions import ExpressionBinding, ExpressionCompiler
from app.text_to_sql.join_policy import ApprovedJoin, resolve_join_tree
from app.text_to_sql.query_plan import PlanField, QueryPlan
from app.text_to_sql.schema_context import default_sql_context
from app.text_to_sql.validator import SqlValidator, ValidatedSql


@dataclass(frozen=True)
class SchemaReferences:
    tables: dict[str, str]
    columns: dict[str, tuple[str, str]]
    relationships: dict[str, ApprovedJoin]

    @classmethod
    def from_context(cls, context: DatasetSqlContext) -> "SchemaReferences":
        tables = {f"t{i}": name for i, name in enumerate(sorted(context.table_columns))}
        columns = {
            f"{key}.c{i}": (name, column)
            for key, name in tables.items()
            for i, column in enumerate(sorted(context.table_columns[name]))
        }
        return cls(
            tables,
            columns,
            {
                f"r{i}": edge
                for i, edge in enumerate(
                    sorted(context.approved_joins, key=lambda edge: edge.relationship_id)
                )
            },
        )


@dataclass(frozen=True)
class CompiledQuery:
    validated: ValidatedSql
    parameters: dict[str, Any]
    evidence_sql: str
    result_columns: tuple[ResultColumn, ...] = ()
    grouped: bool = False
    ranking: tuple[str, str] | None = None


class QueryCompiler:
    """Compile the bounded plan subset, then reuse all existing SQL safety checks."""

    @property
    def context(self) -> DatasetSqlContext:
        """Authorized request catalog; semantic binding must use this same snapshot."""
        return self._context

    def __init__(
        self,
        context: DatasetSqlContext,
        *,
        default_schema: bool = False,
        join_v1_enabled: bool | None = None,
    ) -> None:
        if default_schema and context != default_sql_context():
            raise ValueError("Default schema compilation requires the declared demo catalog")
        self._default_schema = default_schema
        self._join_v1_enabled = (
            bool(context.approved_joins) if join_v1_enabled is None else join_v1_enabled
        )
        self._context = context
        self.references = SchemaReferences.from_context(context)
        self._validator = SqlValidator(
            context.table_columns,
            context.allowed_schemas,
            max_tables=(
                None
                if default_schema
                else 3
                if len(context.approved_joins) >= 2
                else 2
                if context.approved_joins
                else 1
            ),
            approved_joins=context.approved_joins,
            column_types=context.column_types,
            join_v1_enabled=self._join_v1_enabled,
        )

    def compile(self, plan: QueryPlan) -> CompiledQuery:
        try:
            return self._compile(plan)
        except ValidationError as exc:
            raise SqlValidationError(
                "Invalid query plan contract",
                error_context=ErrorContext(
                    origin_stage="plan_compilation",
                    phase="compilation",
                    error_category="sql_validation",
                    **{"validation_branch": "compiler_contract", **validation_context(exc)},
                ),
            ) from exc
        except KeyError as exc:
            raise SqlValidationError(
                "Unknown authorized reference", branch="unknown_reference"
            ) from exc
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise SqlValidationError(
                "Query plan references or values are invalid", branch="compiler_contract"
            ) from exc

    def _compile(self, plan: QueryPlan) -> CompiledQuery:
        plan = QueryPlan.model_validate(plan.model_dump())
        root = self.references.tables[plan.source]
        if plan.relationships and self._join_v1_enabled and not self.references.relationships:
            raise SqlUnsupportedError(
                "A JOIN requires a confirmed relationship",
                reason="relationship",
                code="join_relationship",
            )
        if len(set(plan.relationships)) != len(plan.relationships):
            raise SqlValidationError(
                "Duplicate relationship requirements", branch="duplicate_relationship"
            )
        edges = tuple(self.references.relationships[key] for key in plan.relationships)
        if not self._default_schema and len(edges) > 2:
            raise SqlUnsupportedError(
                "Uploaded JOIN supports at most three tables", code="join_graph"
            )
        if edges:
            names = {n for e in edges for n in (e.source_table, e.target_table)}
            available = tuple(
                e
                for e in self._context.approved_joins
                if e.source_table in names and e.target_table in names
            )
            if set(edges) != set(available):
                raise SqlUnsupportedError("Ambiguous approved JOIN path", code="join_graph")
            if self._default_schema:
                visited, pending, ordered = {root}, list(edges), []
                while pending:
                    edge = next(
                        (
                            e
                            for e in pending
                            if e.source_table in visited and e.target_table not in visited
                        ),
                        None,
                    )
                    if edge is None:
                        raise SqlUnsupportedError("Invalid demo fact tree", code="join_graph")
                    ordered.append(edge)
                    visited.add(edge.target_table)
                    pending.remove(edge)
                edges = tuple(ordered)
            else:
                tree = resolve_join_tree(edges) if len(edges) == 2 else None
                if root != (tree.fact_table if tree else edges[0].source_table):
                    raise SqlUnsupportedError(
                        "Plan source is not the verified fact",
                        code="join_grain",
                        grain_reason="fact_source",
                    )
                edges = tree.relationships if tree else edges
        metadata = MetaData()
        used_tables = {root} | {n for e in edges for n in (e.source_table, e.target_table)}
        tables = {
            name: Table(
                name,
                metadata,
                *(
                    Column(column, SQL_TYPES[self._context.column_types[name][column]]())
                    for column in sorted(self._context.table_columns[name])
                ),
                schema=self._context.allowed_schemas.get(name),
            ).alias(f"q{i}")
            for i, name in enumerate(sorted(used_tables))
        }

        def column(reference: str) -> ColumnElement:
            table, name = self.references.columns[reference]
            if table not in tables:
                raise SqlValidationError(
                    "Column is outside the selected JOIN path", branch="column_scope"
                )
            return tables[table].c[name]

        def column_kind(reference: str) -> str:
            table, name = self.references.columns[reference]
            return self._context.column_types[table][name]

        expressions = ExpressionCompiler(plan.expressions, column, column_kind, self._value)

        aliases = [field.alias for field in plan.fields]
        if len(set(aliases)) != len(aliases) or any(
            len(name.encode("utf-8")) > 63 for name in aliases
        ):
            raise SqlValidationError("Plan output aliases must be unique", branch="output_alias")
        outputs = {}
        output_bindings = []
        result_columns = []
        for field in plan.fields:
            if field.aggregate == "row_count":
                if field.reference is not None:
                    raise SqlValidationError(
                        "Row count does not take a value column", branch="expression_arity"
                    )
                expression = func.count()
                binding = ExpressionBinding(expression, "BIGINT", True)
            else:
                if field.reference is None:
                    raise SqlValidationError(
                        "A column reference is required", branch="unknown_reference"
                    )
                binding = expressions.resolve(field.reference)
                expression = binding.sql
                if field.aggregate:
                    if (
                        binding.aggregate
                        or binding.kind == "BOOLEAN"
                        and field.aggregate != "value_count"
                    ):
                        raise SqlValidationError(
                            "Invalid nested aggregate", branch="nested_aggregate"
                        )
                    if field.aggregate in {"sum", "avg"} and binding.kind not in {
                        "BIGINT",
                        "NUMERIC",
                    }:
                        raise SqlValidationError(
                            "A numeric measure is required", branch="expression_type"
                        )
                    aggregate = {
                        "sum": func.sum,
                        "avg": func.avg,
                        "min": func.min,
                        "max": func.max,
                        "value_count": func.count,
                    }[field.aggregate]
                    expression = aggregate(expression)
                    kind = (
                        "BIGINT"
                        if field.aggregate == "value_count"
                        else "NUMERIC"
                        if field.aggregate in {"sum", "avg"}
                        else binding.kind
                    )
                    binding = ExpressionBinding(expression, kind, True)
            output_bindings.append((field.reference, binding))
            if field.alias in {"matched_row_count", "fact_row_count", "fact_value_count"} and (
                not isinstance(expression, FunctionElement) or expression.name != "count"
            ):
                raise SqlValidationError(
                    "Count aliases require a direct count metric", branch="count_alias"
                )
            if self._default_schema and edges:
                for aggregate in visitors.iterate(expression):
                    if not isinstance(aggregate, FunctionElement) or aggregate.name not in {
                        "sum",
                        "avg",
                        "min",
                        "max",
                    }:
                        continue
                    for argument in visitors.iterate(aggregate.clauses):
                        table = getattr(argument, "table", None)
                        if table is not None and table.original.name != root:
                            raise SqlUnsupportedError(
                                "Cannot aggregate a demo dimension measure",
                                code="join_grain",
                                grain_reason="dimension_measure",
                            )
            outputs[field.alias] = expression.label(field.alias)
            result_columns.append(self._result_column(field, binding, plan))
        has_aggregate = any(binding.aggregate for _, binding in output_bindings)
        grouped_columns = {ref for ref in plan.group_by if ref in self.references.columns}
        if has_aggregate or plan.group_by:
            for reference, binding in output_bindings:
                if reference not in plan.group_by and not binding.ungrouped <= grouped_columns:
                    raise SqlValidationError(
                        "Projection is outside the grouping grain", branch="projection_grain"
                    )
        source = tables[root]
        for edge in edges:
            source = source.join(
                tables[edge.target_table],
                tables[edge.source_table].c[edge.source_column]
                == tables[edge.target_table].c[edge.target_column],
            )
        query = select(*outputs.values()).select_from(source)
        if plan.where:
            predicate = expressions.resolve(plan.where)
            if predicate.kind != "BOOLEAN" or predicate.aggregate or predicate.temporal_transform:
                raise SqlValidationError(
                    "WHERE requires a nonaggregate predicate", branch="where_predicate"
                )
            query = query.where(predicate.sql)
        predicates = []
        for index, condition in enumerate(plan.filters):
            binding = expressions.resolve(condition.reference)
            if binding.aggregate or binding.temporal_transform:
                raise SqlValidationError(
                    "WHERE requires unchanged temporal source columns", branch="where_predicate"
                )
            target = binding.sql
            if condition.operator in {"is_null", "is_not_null"}:
                if condition.values:
                    raise SqlValidationError(
                        "NULL predicates cannot take values", branch="filter_arity"
                    )
                predicates.append(
                    target.is_(None) if condition.operator == "is_null" else target.is_not(None)
                )
                continue
            if not condition.values or (condition.operator != "in" and len(condition.values) != 1):
                raise SqlValidationError("Filter arity is invalid", branch="filter_arity")
            kind = binding.kind
            values = [self._value(value, kind) for value in condition.values]
            parameter = bindparam(
                f"value_{index}",
                values if condition.operator == "in" else values[0],
                type_=target.type,
                expanding=condition.operator == "in",
            )
            comparisons = {"eq": eq, "ne": ne, "gt": gt, "gte": ge, "lt": lt, "lte": le}
            predicates.append(
                target.in_(parameter)
                if condition.operator == "in"
                else comparisons[condition.operator](target, parameter)
            )
        if predicates:
            query = query.where(and_(*predicates))
        if plan.group_by:
            grouped = [expressions.resolve(ref) for ref in plan.group_by]
            if any(item.aggregate or item.kind == "BOOLEAN" for item in grouped):
                raise SqlValidationError(
                    "Invalid grouping expression", branch="grouping_expression"
                )
            query = query.group_by(*(item.sql for item in grouped))
        if plan.having:
            predicate = expressions.resolve(plan.having)
            if predicate.kind != "BOOLEAN" or not predicate.aggregate:
                raise SqlValidationError(
                    "HAVING requires an aggregate predicate", branch="having_predicate"
                )
            if not predicate.ungrouped <= grouped_columns:
                raise SqlValidationError(
                    "HAVING is outside the grouping grain", branch="having_grain"
                )
            query = query.having(predicate.sql)
        for sort in plan.sort:
            if sort.field in outputs:
                expression = outputs[sort.field]
            else:
                binding = expressions.resolve(sort.field)
                if (
                    (has_aggregate or plan.group_by)
                    and sort.field not in plan.group_by
                    and (not binding.ungrouped <= grouped_columns)
                ):
                    raise SqlValidationError(
                        "Sort is outside the grouping grain", branch="sort_grain"
                    )
                expression = binding.sql
            ordered = expression.desc() if sort.direction == "desc" else expression.asc()
            query = query.order_by(
                ordered.nulls_first() if sort.nulls == "first" else ordered.nulls_last()
            )
        if plan.limit:
            query = query.limit(plan.limit)
        dialect = postgresql.dialect(paramstyle="named")
        dialect.bind_typing = BindTyping.NONE
        compiled = query.compile(dialect=dialect, compile_kwargs={"render_postcompile": True})
        # Validate a safely rendered preview so current COUNT/grain analysis sees actual AST values.
        preview = str(query.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
        checked = self._validator.validate(preview, grouping=plan.grouping)
        if (
            checked.statement
            != self._validator.validate(checked.statement, grouping=plan.grouping).statement
        ):
            raise SqlValidationError("Final SQL validation is not stable", branch="ast_stability")
        parameterized = self._validator.validate(str(compiled), grouping=plan.grouping)
        if self._default_schema and edges:

            def provenance(validated: ValidatedSql) -> ValidatedSql:
                ast = parse_one(validated.statement, read="postgres")
                aliases = {table.alias_or_name: table.name for table in ast.find_all(exp.Table)}
                counts = analyze_counts(
                    ast,
                    aliases,
                    root,
                    edges,
                    normalize=False,
                    input_names=set().union(*self._context.table_columns.values()),
                )
                return replace(
                    validated,
                    fact_table=root,
                    count_metrics=counts,
                    relationship_ids=tuple(edge.relationship_id for edge in edges),
                )

            checked, parameterized = provenance(checked), provenance(parameterized)
        if (parameterized.tables, parameterized.fact_table, parameterized.count_metrics) != (
            checked.tables,
            checked.fact_table,
            checked.count_metrics,
        ):
            raise SqlValidationError(
                "Bound SQL changed validated query provenance", branch="provenance_mismatch"
            )
        if parse_one(str(compiled), read="postgres").sql(dialect="postgres") != (
            parameterized.statement
        ):
            raise SqlValidationError(
                "Compiled query would require AST normalization", branch="ast_normalization"
            )
        row_counts = {
            metric.output_alias for metric in checked.count_metrics if metric.kind == "row_count"
        }
        result_columns = [
            column.model_copy(
                update={"label": "Số bản ghi", "aggregate": "row_count", "source_label": None}
            )
            if column.key in row_counts
            else column
            for column in result_columns
        ]
        return CompiledQuery(
            replace(parameterized, statement=str(compiled)),
            dict(compiled.params),
            checked.statement,
            tuple(result_columns),
            bool(plan.group_by),
            (plan.sort[0].field, plan.sort[0].direction) if plan.limit == 1 and plan.sort else None,
        )

    def _result_column(
        self, field: PlanField, binding: ExpressionBinding, plan: QueryPlan
    ) -> ResultColumn:
        """Describe actual expression lineage, not business semantics from an alias."""
        location = self.references.columns.get(field.reference)
        direct = location if field.aggregate is None else None
        node = (
            plan.expressions[int(field.reference[1:])]
            if field.reference and field.reference.startswith("e")
            else None
        )
        operation = field.aggregate
        if operation is None and node is not None:
            operation = (
                node.operation
                if node.operation in {"sum", "avg", "min", "max", "row_count", "value_count"}
                else None
            )
            location = (
                self.references.columns.get(node.arguments[0]) if len(node.arguments) == 1 else None
            )
        literal = node is not None and node.operation == "literal" and field.aggregate is None
        identifier = direct is not None and any(
            direct
            in {(edge.source_table, edge.source_column), (edge.target_table, edge.target_column)}
            for edge in self._context.approved_joins
        )
        numeric = (
            binding.kind in {"BIGINT", "NUMERIC"}
            and not identifier
            and (binding.aggregate or binding.kind == "NUMERIC" and not binding.temporal_transform)
        )
        header = (
            self._context.column_headers.get(location[0], {}).get(location[1], location[1])
            if location
            else None
        )
        source_label = column_label(header) if header else None
        label = (source_label or column_label(direct[1])) if direct else "Kết quả tính toán"
        if literal:
            label = "Hằng số " + binding.kind
        if operation is not None:
            prefix = {
                "sum": "Tổng",
                "avg": "Trung bình",
                "min": "Nhỏ nhất",
                "max": "Lớn nhất",
                "row_count": "Số bản ghi",
                "value_count": "Số giá trị có dữ liệu",
            }[operation]
            label = prefix + (
                " " + source_label if source_label and operation != "row_count" else ""
            )
        return ResultColumn(
            key=field.alias,
            label=label,
            numeric=numeric,
            data_type=binding.kind,
            provenance="literal"
            if literal
            else "aggregate"
            if binding.aggregate
            else "column"
            if direct
            else "expression",
            aggregate=operation,
            source_label=source_label,
        )

    @staticmethod
    def _value(value: str, kind: str) -> Any:
        try:
            return QueryCompiler._parse_value(value, kind)
        except (ValueError, TypeError, InvalidOperation, OverflowError) as exc:
            raise SqlValidationError("Invalid typed literal", branch="literal_value") from exc

    @staticmethod
    def _parse_value(value: str, kind: str) -> Any:
        if kind == "NUMERIC":
            result = Decimal(value)
            if not result.is_finite():
                raise ValueError("Non-finite numeric")
            return result
        if kind == "BIGINT":
            integer = int(value)
            if not -(2**63) <= integer < 2**63:
                raise ValueError("Integer is outside PostgreSQL BIGINT bounds")
            return integer
        if kind == "BOOLEAN":
            if value not in {"true", "false"}:
                raise ValueError("Invalid boolean")
            return value == "true"
        if kind == "DATE":
            return date.fromisoformat(value)
        if kind in {"TIMESTAMP", "TIMESTAMPTZ"}:
            result = datetime.fromisoformat(value)
            if kind == "TIMESTAMPTZ" and result.tzinfo is None:
                raise ValueError("A timezone is required")
            if kind == "TIMESTAMP" and result.tzinfo is not None:
                raise ValueError("Cannot discard a timestamp offset")
            return result
        if kind != "TEXT":
            raise ValueError("Unknown registry type")
        return value
