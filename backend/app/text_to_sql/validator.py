"""AST-based validator for the supported read-only PostgreSQL subset."""

from dataclasses import dataclass, field
from typing import Literal

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.core.diagnostics import diagnostic_stage
from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.text_to_sql.count_contract import (
    CountMetric,
    analyze_counts,
    output_field_name,
    record_aggregate_shape,
)
from app.text_to_sql.join_policy import (
    ApprovedJoin,
    validate_uploaded_join,
    validate_uploaded_join_tree,
)
from app.text_to_sql.schema_context import TABLE_COLUMNS

ALLOWED_FUNCTIONS = {
    "and",
    "avg",
    "cast",
    "coalesce",
    "count",
    "date_trunc",
    "extract",
    "max",
    "min",
    "nullif",
    "or",
    "round",
    "sum",
    "time_to_str",
    "timestamp_trunc",
    "timezone",
    "to_char",
}

PROHIBITED_NODES = (
    exp.Alter,
    exp.Command,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Into,
    exp.Lock,
    exp.Merge,
    exp.Subquery,
    exp.Update,
    exp.With,
    exp.Window,
)


@dataclass
class ValidatedSql:
    statement: str
    tables: frozenset[str]
    relationship_id: str | None = None
    fact_table: str | None = None
    relationship_ids: tuple[str, ...] = ()
    count_metrics: tuple[CountMetric, ...] = field(default=(), repr=False)


class SqlValidator:
    """Validate syntax, referenced objects, functions, and unsupported AST nodes."""

    def __init__(
        self,
        table_columns: dict[str, set[str]] | None = None,
        allowed_schemas: dict[str, str] | None = None,
        max_tables: int | None = None,
        approved_joins: tuple[ApprovedJoin, ...] = (),
        column_types: dict[str, dict[str, str]] | None = None,
        join_v1_enabled: bool = False,
    ) -> None:
        self._table_columns = {
            table.lower(): {column.lower() for column in columns}
            for table, columns in (table_columns or TABLE_COLUMNS).items()
        }
        self._allowed_schemas = {
            table.lower(): schema.lower() for table, schema in (allowed_schemas or {}).items()
        }
        self._max_tables = max_tables
        self._approved_joins = approved_joins
        self._column_types = column_types or {}
        self._join_v1_enabled = join_v1_enabled

    @diagnostic_stage("sql_validation")
    def validate(
        self, sql: str, *, grouping: Literal["entity", "category"] = "entity"
    ) -> ValidatedSql:
        with diagnostic_stage("sql_parse_error"):
            if not sql.strip():
                raise SqlValidationError("SQL is empty")
            try:
                statements = parse(sql, read="postgres")
            except ParseError as exc:
                raise SqlValidationError("SQL syntax is invalid") from exc
            if len(statements) != 1:
                raise SqlValidationError("Exactly one SQL statement is required")
            root = statements[0]
            if not isinstance(root, exp.Select):
                raise SqlValidationError("Only SELECT statements are supported")
            if any(root.find(node_type) is not None for node_type in PROHIBITED_NODES):
                raise SqlValidationError("SQL contains an unsupported or unsafe construct")
            if root.args.get("locks"):
                raise SqlValidationError("Row locking is not supported")

        with diagnostic_stage("schema_metadata"):
            tables, aliases = self._validate_tables(root)
            self._validate_functions(root)
        with diagnostic_stage("column_resolution"):
            self._validate_columns(root, aliases)
        relation = None
        tree = None
        counts: tuple[CountMetric, ...] = ()
        with diagnostic_stage("join_graph"):
            if self._max_tables is not None and root.find(exp.Join) is not None:
                if not self._join_v1_enabled:
                    raise SqlValidationError("Uploaded JOIN v1 is disabled")
                for normalize in (True, False):
                    if len(tables) == 3:
                        tree = validate_uploaded_join_tree(
                            root,
                            aliases,
                            self._approved_joins,
                            self._column_types,
                            self._table_columns,
                            normalize_counts=normalize,
                            grouping=grouping,
                        )
                        metrics = tree.count_metrics
                    else:
                        relation, metrics = self._validate_two_table_join(
                            root, aliases, normalize, grouping=grouping
                        )
                    if normalize:
                        counts = metrics
                    elif metrics != counts:
                        raise SqlValidationError("Normalized COUNT provenance changed")
                    tables, aliases = self._validate_tables(root)
                    self._validate_functions(root)
                    self._validate_columns(root, aliases)
            elif len(tables) == 1:
                names = self._table_columns[next(iter(tables))]
                counts = analyze_counts(root, aliases, next(iter(tables)), input_names=names)
                tables, aliases = self._validate_tables(root)
                self._validate_functions(root)
                self._validate_columns(root, aliases)
                if (
                    analyze_counts(
                        root, aliases, next(iter(tables)), normalize=False, input_names=names
                    )
                    != counts
                ):
                    raise SqlValidationError("Normalized COUNT provenance changed")
        return ValidatedSql(
            statement=root.sql(dialect="postgres"),
            tables=frozenset(tables),
            relationship_id=relation.relationship_id if relation else None,
            fact_table=tree.fact_table if tree else relation.source_table if relation else None,
            relationship_ids=tuple(r.relationship_id for r in tree.relationships) if tree else (),
            count_metrics=counts,
        )

    def _validate_two_table_join(
        self,
        root: exp.Select,
        aliases: dict[str, str],
        normalize: bool = True,
        *,
        grouping: Literal["entity", "category"] = "entity",
    ) -> tuple[ApprovedJoin, tuple[CountMetric, ...]]:
        try:
            relation, counts = validate_uploaded_join(
                root,
                aliases,
                self._approved_joins,
                self._column_types,
                self._table_columns,
                normalize_counts=normalize,
                grouping=grouping,
            )
        except SqlUnsupportedError as exc:
            if exc.code != "join_direction":
                raise
            # The policy proved a single INNER equality on one approved key pair.
            source, join = root.args["from_"], root.args["joins"][0]
            dimension, fact = source.this, join.this
            source.set("this", fact.copy())
            join.set("this", dimension.copy())
            _, aliases = self._validate_tables(root)
            self._validate_functions(root)
            self._validate_columns(root, aliases)
            relation, counts = validate_uploaded_join(
                root,
                aliases,
                self._approved_joins,
                self._column_types,
                self._table_columns,
                normalize_counts=normalize,
                grouping=grouping,
            )
        return relation, counts

    def _validate_tables(self, root: exp.Select) -> tuple[set[str], dict[str, str]]:
        tables: set[str] = set()
        aliases: dict[str, str] = {}
        for table in root.find_all(exp.Table):
            table_name = table.name.lower()
            allowed_schema = self._allowed_schemas.get(table_name)
            referenced_schema = table.db.lower() if table.db else None
            if (
                table.catalog
                or table_name not in self._table_columns
                or referenced_schema != allowed_schema
            ):
                raise SqlValidationError(f"Table is not allowed: {table.sql()}")
            tables.add(table_name)
            visible_name = table.alias_or_name.lower()
            if visible_name in aliases:
                raise SqlValidationError(f"Duplicate table alias: {visible_name}")
            aliases[visible_name] = table_name
        if not tables:
            raise SqlValidationError("A business table is required")
        if self._max_tables == 1 and root.find(exp.Join) is not None:
            if self._join_v1_enabled:
                raise SqlUnsupportedError(
                    "A JOIN requires a confirmed relationship",
                    reason="relationship",
                    code="join_relationship",
                )
            raise SqlValidationError("JOIN is not supported without declared relationship metadata")
        if self._max_tables is not None and len(tables) > self._max_tables:
            raise SqlValidationError("Multiple tables require declared relationship metadata")
        return tables, aliases

    @staticmethod
    def _validate_functions(root: exp.Select) -> None:
        for function in root.find_all(exp.Func):
            function_name = function.sql_name().lower()
            if function_name not in ALLOWED_FUNCTIONS:
                raise SqlValidationError(f"Function is not allowed: {function_name}")

    def _validate_columns(self, root: exp.Select, aliases: dict[str, str]) -> None:
        projection_aliases: dict[str, list[exp.Expression]] = {}
        for expression in root.expressions:
            if isinstance(expression, exp.Alias):
                projection_aliases.setdefault(output_field_name(expression), []).append(
                    expression.this
                )
            elif isinstance(expression, exp.Count):
                projection_aliases.setdefault("count", []).append(expression)
        for column in root.find_all(exp.Column):
            column_name = column.name.lower()
            reference_name = output_field_name(column)
            qualifier = column.table.lower()
            if qualifier:
                table_name = aliases.get(qualifier)
                if not table_name or column_name not in self._table_columns[table_name]:
                    raise SqlValidationError(f"Column is not allowed: {column.sql()}")
                if column.catalog or (
                    column.db
                    and (
                        qualifier != table_name
                        or column.db.lower() != self._allowed_schemas.get(table_name)
                    )
                ):
                    raise SqlValidationError(f"Column schema is not allowed: {column.sql()}")
                continue
            matching_tables = [
                table for table in aliases.values() if column_name in self._table_columns[table]
            ]
            parent = column.parent
            order_alias = isinstance(parent, exp.Ordered) and parent.parent is root.args.get(
                "order"
            )
            group_alias = isinstance(parent, exp.Group) and parent is root.args.get("group")
            # PostgreSQL ORDER BY prefers output names; GROUP BY prefers input names.
            if (order_alias or group_alias and not matching_tables) and (
                reference_name in projection_aliases
            ):
                expressions = projection_aliases[reference_name]
                if any(expression != expressions[0] for expression in expressions[1:]):
                    count = next(
                        (e.find(exp.Count) for e in expressions if e.find(exp.Count) is not None),
                        None,
                    )
                    if count is not None:
                        record_aggregate_shape(root, count)
                        raise SqlUnsupportedError(
                            "COUNT output reference is ambiguous",
                            reason="calculation",
                            code="join_aggregate",
                            aggregate_reason="count_projection_alias_ambiguous",
                        )
                    raise SqlValidationError(f"Ambiguous output alias: {column_name}")
                continue
            if len(matching_tables) != 1:
                raise SqlValidationError(
                    f"Unqualified column is unknown or ambiguous: {column_name}"
                )
