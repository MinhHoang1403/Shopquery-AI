"""Backend-owned INNER JOIN authorization with one preserved root fact grain."""

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
    joins, _ = _validate_binding_shape(root, aliases, 2)
    relationship = _approved_equality(joins[0], aliases, relationships)
    if (
        root.args["from_"].this.name.lower() != relationship.source_table
        or joins[0].this.name.lower() != relationship.target_table
    ):
        raise SqlUnsupportedError(
            "Equivalent INNER JOIN bindings are in dimension-to-fact order",
            reason="calculation",
            code="join_direction",
        )
    _validate_join_aggregates(
        root,
        aliases,
        relationship.source_table,
        {relationship.source_column},
        column_types,
        table_columns,
    )
    return relationship


@dataclass(frozen=True)
class JoinTree:
    fact_table: str
    relationships: tuple[ApprovedJoin, ...]


def resolve_join_tree(relationships: tuple[ApprovedJoin, ...]) -> JoinTree:
    names = {name for r in relationships for name in (r.source_table, r.target_table)}
    roots = names - {r.target_table for r in relationships}
    if (
        len(relationships) != 2
        or len(names) != 3
        or len(roots) != 1
        or (len({r.relationship_id for r in relationships}) != 2)
    ):
        raise SqlUnsupportedError(
            "Three tables require two unambiguous relationships and one root fact",
            reason="calculation",
            code="join_graph",
        )
    fact = next(iter(roots))
    visited, ordered = {fact}, []
    pending = sorted(relationships, key=lambda r: (r.source_table, r.target_table))
    while pending:
        edge = next(
            (r for r in pending if r.source_table in visited and r.target_table not in visited),
            None,
        )
        if edge is None:
            raise SqlUnsupportedError(
                "JOIN graph would introduce a second fact, cycle or fan-out",
                reason="calculation",
                code="join_graph",
            )
        ordered.append(edge)
        visited.add(edge.target_table)
        pending.remove(edge)
    return JoinTree(fact, tuple(ordered))


def validate_uploaded_join_tree(
    root: exp.Select,
    aliases: dict[str, str],
    relationships: tuple[ApprovedJoin, ...],
    column_types: dict[str, dict[str, str]],
    table_columns: dict[str, set[str]],
) -> JoinTree:
    joins, bindings = _validate_binding_shape(root, aliases, 3)
    names = set(aliases.values())
    plan = resolve_join_tree(
        tuple(r for r in relationships if r.source_table in names and r.target_table in names)
    )
    seen = {root.args["from_"].this.name.lower()}
    matched = {}
    for join in joins:
        relation = _approved_equality(join, aliases, plan.relationships)
        added = join.this.name.lower()
        ends = {relation.source_table, relation.target_table}
        if added in seen or added not in ends or len(ends & seen) != 1:
            raise SqlValidationError("Each ON must connect the new table to an earlier binding")
        seen.add(added)
        matched[relation.relationship_id] = join
    if set(matched) != {r.relationship_id for r in plan.relationships}:
        raise SqlValidationError("Both verified relationships must appear exactly once")
    # Only verified INNER equalities are reordered; aliases, projections and filters are preserved.
    tables = {binding.name.lower(): binding for binding in bindings}
    root.args["from_"].set("this", tables[plan.fact_table].copy())
    normalized = []
    for relation in plan.relationships:
        join = matched[relation.relationship_id].copy()
        join.set("this", tables[relation.target_table].copy())
        normalized.append(join)
    root.set("joins", normalized)
    _validate_binding_shape(root, aliases, 3)
    _validate_join_aggregates(
        root,
        aliases,
        plan.fact_table,
        {r.source_column for r in plan.relationships if r.source_table == plan.fact_table},
        column_types,
        table_columns,
    )
    return plan


def _validate_binding_shape(
    root: exp.Select,
    aliases: dict[str, str],
    count: int,
) -> tuple[list[exp.Join], list[exp.Table]]:
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
    if len(joins) != count - 1 or len(bindings) != count or len(set(aliases.values())) != count:
        raise SqlValidationError(
            "JOIN requires two or three distinct bindings and one verified edge per added table"
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
    return joins, bindings


def _approved_equality(
    join: exp.Join,
    aliases: dict[str, str],
    relationships: tuple[ApprovedJoin, ...],
) -> ApprovedJoin:
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
    names = {name for name, _ in endpoints}
    candidates = [item for item in relationships if names == {item.source_table, item.target_table}]
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
    return relationship


def _validate_join_aggregates(
    root: exp.Select,
    aliases: dict[str, str],
    fact_table: str,
    fact_join_keys: set[str],
    column_types: dict[str, dict[str, str]],
    table_columns: dict[str, set[str]],
) -> None:
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
            "JOIN aggregates cannot use FILTER",
            reason="calculation",
            code="join_aggregate",
            aggregate_reason="filter",
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
                aggregate_reason="projection_expression",
            )
    for aggregate in root.find_all(exp.AggFunc):
        argument = aggregate.this
        if aggregate.expressions:
            raise SqlUnsupportedError(
                "JOIN aggregates require one direct column",
                reason="calculation",
                code="join_aggregate",
                aggregate_reason="multiple_arguments",
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
                    aggregate_reason="count_star_alias",
                )
            continue
        if not isinstance(argument, exp.Column):
            raise SqlUnsupportedError(
                "JOIN aggregates require a direct fact column",
                reason="calculation",
                code="join_aggregate",
                aggregate_reason="argument_expression",
            )
        if aliases.get(argument.table.lower()) != fact_table:
            raise SqlUnsupportedError(
                "Cannot aggregate a dimension column",
                reason="calculation",
                code="join_aggregate",
                aggregate_reason="dimension_column",
            )
        if isinstance(aggregate, exp.Count):
            output = aggregate.parent
            if (
                argument.name.lower() in fact_join_keys
                and isinstance(output, exp.Alias)
                and output.alias.lower() in {"fact_row_count", "matched_row_count"}
            ):
                # Equality in this verified INNER JOIN excludes NULL keys from matched rows.
                aggregate.set("this", exp.Star())
                continue
            if not isinstance(output, exp.Alias) or output.alias.lower() != "fact_value_count":
                raise SqlUnsupportedError(
                    "COUNT(column) requires fact_value_count",
                    reason="calculation",
                    code="join_aggregate",
                    aggregate_reason="count_column_alias",
                )
        else:
            if not isinstance(aggregate, (exp.Sum, exp.Avg)):
                raise SqlUnsupportedError(
                    "Only COUNT/SUM/AVG are supported in uploaded JOIN v1",
                    reason="calculation",
                    code="join_aggregate",
                    aggregate_reason="unsupported_function",
                )
            if column_types.get(fact_table, {}).get(argument.name.lower()) not in {
                "BIGINT",
                "NUMERIC",
            }:
                raise SqlUnsupportedError(
                    "SUM/AVG require a numeric fact column",
                    reason="calculation",
                    code="join_aggregate",
                    aggregate_reason="non_numeric_fact",
                )
