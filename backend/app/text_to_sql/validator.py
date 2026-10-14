"""AST-based validator for the supported read-only PostgreSQL subset."""

from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.core.errors import SqlValidationError
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
)


@dataclass
class ValidatedSql:
    statement: str
    tables: frozenset[str]


class SqlValidator:
    """Validate syntax, referenced objects, functions, and unsupported AST nodes."""

    def __init__(
        self,
        table_columns: dict[str, set[str]] | None = None,
        allowed_schemas: dict[str, str] | None = None,
    ) -> None:
        self._table_columns = {
            table.lower(): {column.lower() for column in columns}
            for table, columns in (table_columns or TABLE_COLUMNS).items()
        }
        self._allowed_schemas = {
            table.lower(): schema.lower()
            for table, schema in (allowed_schemas or {}).items()
        }

    def validate(self, sql: str) -> ValidatedSql:
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

        tables, aliases = self._validate_tables(root)
        self._validate_functions(root)
        self._validate_columns(root, tables, aliases)
        return ValidatedSql(statement=root.sql(dialect="postgres"), tables=frozenset(tables))

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
            aliases[table.alias_or_name.lower()] = table_name
            aliases[table_name] = table_name
        if not tables:
            raise SqlValidationError("A business table is required")
        return tables, aliases

    @staticmethod
    def _validate_functions(root: exp.Select) -> None:
        for function in root.find_all(exp.Func):
            function_name = function.sql_name().lower()
            if function_name not in ALLOWED_FUNCTIONS:
                raise SqlValidationError(f"Function is not allowed: {function_name}")

    def _validate_columns(
        self, root: exp.Select, tables: set[str], aliases: dict[str, str]
    ) -> None:
        projection_aliases = {
            expression.alias.lower()
            for expression in root.expressions
            if expression.alias
        }
        for column in root.find_all(exp.Column):
            column_name = column.name.lower()
            qualifier = column.table.lower()
            if column_name in projection_aliases and not qualifier:
                continue
            if qualifier:
                table_name = aliases.get(qualifier)
                if not table_name or column_name not in self._table_columns[table_name]:
                    raise SqlValidationError(f"Column is not allowed: {column.sql()}")
                continue
            matching_tables = [
                table for table in tables if column_name in self._table_columns[table]
            ]
            if len(matching_tables) != 1:
                raise SqlValidationError(
                    f"Unqualified column is unknown or ambiguous: {column_name}"
                )
