"""Backend-owned authorization for one uploaded fact-to-dimension INNER JOIN."""

from dataclasses import dataclass

from sqlglot import exp

from app.core.errors import SqlUnsupportedError, SqlValidationError


@dataclass(frozen=True)
class ApprovedJoin:
    relationship_id: str
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    revision: str


def validate_uploaded_join(
    root: exp.Select,
    aliases: dict[str, str],
    relationships: tuple[ApprovedJoin, ...],
    column_types: dict[str, dict[str, str]],
    table_columns: dict[str, set[str]],
) -> ApprovedJoin:
    joins, bindings = list(root.find_all(exp.Join)), list(root.find_all(exp.Table))
    if len(list(root.find_all(exp.Select))) != 1:
        raise SqlValidationError("Nested SELECT scopes are unsupported in JOIN v1")
    if any(node.comments for node in root.walk()):
        raise SqlValidationError("Comments are not supported in uploaded JOIN v1")
    if any(
        identifier.quoted and identifier.name != identifier.name.lower()
        for identifier in root.find_all(exp.Identifier)
    ):
        raise SqlValidationError("Identifiers must match the normalized metadata exactly")
    if len(joins) != 1 or len(bindings) != 2 or len(set(aliases.values())) != 2:
        raise SqlValidationError(
            "JOIN v1 requires exactly two distinct table bindings and one join"
        )
    if any(not isinstance(item.this, exp.Identifier) or not item.alias for item in bindings):
        raise SqlValidationError("JOIN v1 requires ordinary tables and explicit aliases")
    if any(
        item.args.get("alias").args.get("columns")
        or any(value for key, value in item.args.items() if key not in {"this", "db", "alias"})
        for item in bindings
    ):
        raise SqlValidationError("Table decorations and renamed column lists are unsupported")
    names = {item.name.lower() for item in bindings}
    if any(alias in names and alias != name for alias, name in aliases.items()):
        raise SqlValidationError("Table aliases cannot shadow another table")
    join = joins[0]
    if (
        join.args.get("side")
        or join.args.get("method")
        or join.args.get("using")
        or (join.args.get("kind") or "").upper() not in {"", "INNER"}
        or not isinstance(join.this, exp.Table)
        or any(value for key, value in join.args.items() if key not in {"this", "on", "kind"})
    ):
        raise SqlValidationError("Only explicit INNER JOIN ON is supported")
    predicate = join.args.get("on")
    while isinstance(predicate, exp.Paren):
        predicate = predicate.this
    if not isinstance(predicate, exp.EQ) or not all(
        isinstance(value, exp.Column) and value.table
        for value in (predicate.this, predicate.expression)
    ):
        raise SqlValidationError("JOIN ON must be exactly one approved column equality")
    endpoints = {
        (aliases.get(value.table.lower()), value.name.lower())
        for value in (predicate.this, predicate.expression)
    }
    source = root.args["from_"].this.name.lower()
    target = join.this.name.lower()
    candidates = [
        item for item in relationships if {source, target} == {item.source_table, item.target_table}
    ]
    if len(candidates) != 1:
        raise SqlUnsupportedError(
            "JOIN requires exactly one approved relationship for its table pair",
            reason="relationship",
            code="join_relationship",
        )
    relationship = candidates[0]
    if endpoints != {
        (relationship.source_table, relationship.source_column),
        (relationship.target_table, relationship.target_column),
    }:
        raise SqlUnsupportedError(
            "JOIN ON does not match the approved key pair",
            reason="calculation",
            code="join_key",
        )
    if source != relationship.source_table or target != relationship.target_table:
        raise SqlUnsupportedError(
            "Equivalent INNER JOIN bindings are in dimension-to-fact order",
            reason="calculation",
            code="join_direction",
        )
    output_names = {item.alias.lower() for item in root.expressions if item.alias}
    input_names = set().union(*(table_columns[name] for name in aliases.values()))
    for col in root.find_all(exp.Column):
        if col.table:
            continue
        parent = col.parent
        order_alias = isinstance(parent, exp.Ordered) and parent.parent is root.args.get("order")
        group_alias = (
            isinstance(parent, exp.Group)
            and parent is root.args.get("group")
            and col.name.lower() not in input_names
        )
        if col.name.lower() not in output_names or not (order_alias or group_alias):
            raise SqlValidationError("JOIN v1 requires qualified source columns")
    if root.find(exp.Filter) is not None:
        raise SqlUnsupportedError(
            "JOIN aggregates cannot use FILTER", reason="calculation", code="join_aggregate"
        )
    for projection in root.expressions:
        expression = projection.this if isinstance(projection, exp.Alias) else projection
        if expression.is_star:
            raise SqlValidationError("Select explicit columns in JOIN v1")
        if expression.find(exp.AggFunc) and not isinstance(expression, exp.AggFunc):
            raise SqlUnsupportedError(
                "JOIN projections require direct fact aggregates",
                reason="calculation",
                code="join_aggregate",
            )
    for aggregate in root.find_all(exp.AggFunc):
        argument = aggregate.this
        if aggregate.expressions:
            raise SqlUnsupportedError(
                "JOIN aggregates require one direct column",
                reason="calculation",
                code="join_aggregate",
            )
        if isinstance(aggregate, exp.Count) and isinstance(argument, exp.Star):
            output = aggregate.parent
            if not isinstance(output, exp.Alias) or output.alias.lower() not in {
                "fact_row_count",
                "matched_row_count",
            }:
                raise SqlUnsupportedError(
                    "JOIN COUNT(*) requires a fact-row alias",
                    reason="calculation",
                    code="join_aggregate",
                )
            continue
        if (
            not isinstance(argument, exp.Column)
            or aliases.get(argument.table.lower()) != relationship.source_table
            or aggregate.expressions
        ):
            raise SqlUnsupportedError(
                "Cannot aggregate dimension or expressions",
                reason="calculation",
                code="join_aggregate",
            )
        if isinstance(aggregate, exp.Count):
            output = aggregate.parent
            if not isinstance(output, exp.Alias) or output.alias.lower() != "fact_value_count":
                raise SqlUnsupportedError(
                    "COUNT(column) requires fact_value_count",
                    reason="calculation",
                    code="join_aggregate",
                )
        elif not isinstance(aggregate, (exp.Sum, exp.Avg)) or column_types.get(
            relationship.source_table, {}
        ).get(argument.name.lower()) not in {"BIGINT", "NUMERIC"}:
            raise SqlUnsupportedError(
                "SUM/AVG require a numeric fact column",
                reason="calculation",
                code="join_aggregate",
            )
    return relationship
