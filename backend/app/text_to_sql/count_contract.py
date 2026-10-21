"""COUNT provenance derived from a validated root fact, never from a display alias."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NoReturn

from sqlglot import exp

from app.core.diagnostics import AGGREGATE_FACTS, diagnostic_stage, record_facts
from app.core.errors import JoinAggregateReason, SqlUnsupportedError

if TYPE_CHECKING:
    from app.text_to_sql.join_policy import ApprovedJoin


class CountKind(StrEnum):
    ROW_COUNT = "row_count"
    NON_NULL_VALUE_COUNT = "non_null_value_count"


class NonNullProof(StrEnum):
    STAR = "star_rows"
    INNER_KEY = "verified_inner_equality"
    UNKNOWN = "nullable_or_unknown"


@dataclass(frozen=True)
class CountMetric:
    kind: CountKind
    root_fact: str = field(repr=False)
    fact_column: str | None = field(repr=False)
    output_alias: str = field(repr=False)
    projection_index: int
    non_null_proof: NonNullProof
    relationships: tuple[tuple[str, str], ...] = field(repr=False)
    source_aggregate: exp.Count = field(compare=False, repr=False)
    selected_projection: exp.Expression = field(compare=False, repr=False)
    grouping_grain: tuple[exp.Expression, ...] = field(compare=False, repr=False)
    normalization: tuple[str, ...] = field(default=(), compare=False)

    @property
    def signature(self) -> tuple[CountKind, str, str | None]:
        column = self.fact_column if self.kind == CountKind.NON_NULL_VALUE_COUNT else None
        return self.kind, self.root_fact, column


def aggregate_clause(root: exp.Select, aggregate: exp.Expression) -> str:
    node = aggregate
    while node.parent is not None:
        parent = node.parent
        if parent is root:
            return "select" if node in root.expressions else "other"
        if parent is root.args.get("order"):
            return "order_by"
        if parent is root.args.get("having"):
            return "having"
        if parent is root.args.get("group"):
            return "other"
        node = parent
    return "other"


def record_aggregate_shape(
    root: exp.Select,
    aggregate: exp.AggFunc,
    *,
    row_count: bool = False,
    matching: bool = False,
    candidate: bool = False,
    applied: bool = False,
) -> None:
    """Only finite categories leave this function; telemetry cannot change validation."""
    with suppress(Exception):
        clause = aggregate_clause(root, aggregate)
        parent_type = type(aggregate.parent).__name__
        output = aggregate.parent
        contract = "not_applicable"
        if isinstance(aggregate, exp.Count) and clause == "select":
            contract = "missing" if not isinstance(output, exp.Alias) else "valid"
            if isinstance(output, exp.Alias):
                alias = output.alias.lower()
                if (
                    alias in {"fact_row_count", "matched_row_count"}
                    and not row_count
                    or alias == "fact_value_count"
                    and isinstance(aggregate.this, exp.Star)
                ):
                    contract = "invalid"
        record_facts(
            aggregate_function=aggregate.key
            if aggregate.key in {"count", "sum", "avg"}
            else "other",
            aggregate_clause=clause,
            aggregate_parent_type=parent_type
            if parent_type in AGGREGATE_FACTS["aggregate_parent_type"]
            else "Other",
            count_argument_shape=(
                "not_applicable"
                if not isinstance(aggregate, exp.Count)
                else "star"
                if isinstance(aggregate.this, exp.Star)
                else "column"
                if isinstance(aggregate.this, exp.Column)
                else "expression"
            ),
            projection_alias_contract=contract,
            matching_selected_aggregate=matching,
            normalization_candidate=candidate,
            normalization_applied=applied,
        )


def _refuse(reason: JoinAggregateReason) -> NoReturn:
    raise SqlUnsupportedError(
        "COUNT is outside the verified semantic contract",
        reason="calculation",
        code="join_aggregate",
        aggregate_reason=reason,
    )


def _meaning(
    root: exp.Select,
    count: exp.Count,
    aliases: dict[str, str],
    fact: str,
    keys: set[str],
) -> tuple[CountKind, str | None, NonNullProof]:
    argument = count.this
    row_count = isinstance(argument, exp.Star) or (
        isinstance(argument, exp.Column)
        and aliases.get(argument.table.lower()) == fact
        and argument.name.lower() in keys
    )
    record_aggregate_shape(root, count, row_count=row_count)
    if count.expressions:
        _refuse("multiple_arguments")
    if isinstance(argument, exp.Star):
        if any(argument.args.values()):
            _refuse("argument_expression")
        return CountKind.ROW_COUNT, None, NonNullProof.STAR
    if not isinstance(argument, exp.Column) or argument.is_star:
        _refuse("argument_expression")
    table = (
        aliases.get(argument.table.lower())
        if argument.table
        else fact
        if len(aliases) == 1
        else None
    )
    if table != fact:
        _refuse("dimension_column")
    column = argument.name.lower()
    if column in keys:
        return CountKind.ROW_COUNT, column, NonNullProof.INNER_KEY
    return CountKind.NON_NULL_VALUE_COUNT, column, NonNullProof.UNKNOWN


def _identifier_name(identifier: exp.Identifier) -> str:
    # PostgreSQL UTF8 folds ASCII A-Z only; quoted identifiers are exact.
    return (
        identifier.name
        if identifier.quoted
        else identifier.name.translate(
            str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
        )
    )


def output_field_name(projection: exp.Expression) -> str:
    if projection.is_star:
        return ""
    if isinstance(projection, exp.Alias):
        identifier = projection.args["alias"]
        return _identifier_name(identifier)
    if isinstance(projection, exp.Column):
        if not isinstance(projection.this, exp.Identifier):
            return ""
        return _identifier_name(projection.this)
    if isinstance(projection, exp.AggFunc):
        return projection.sql_name().lower()
    return projection.output_name.lower()


def analyze_counts(
    root: exp.Select,
    aliases: dict[str, str],
    fact: str,
    relationships: tuple[ApprovedJoin, ...] = (),
    *,
    normalize: bool = True,
    input_names: set[str] | None = None,
) -> tuple[CountMetric, ...]:
    """Caller proves graph, exact INNER keys and grain before invoking this analyzer."""
    counts = list(root.find_all(exp.Count))
    if not counts:
        return ()
    keys = {r.source_column for r in relationships if r.source_table == fact}
    selected: list[tuple[int, exp.Expression, exp.Count]] = []
    ordered: list[exp.Count] = []
    meanings: dict[int, tuple[CountKind, str | None, NonNullProof]] = {}
    for count in counts:
        clause = aggregate_clause(root, count)
        record_aggregate_shape(root, count)
        if count.find_ancestor(exp.Filter) is not None:
            _refuse("filter")
        if clause == "having":
            _refuse("count_having_unsupported")
        if count.find_ancestor(exp.Group) is not None:
            _refuse("count_group_reference")
        projection = count.parent if isinstance(count.parent, exp.Alias) else count
        if (
            clause == "select"
            and projection in root.expressions
            and (projection is count or projection.this is count)
        ):
            selected.append((root.expressions.index(projection), projection, count))
        elif clause == "order_by" and isinstance(count.parent, exp.Ordered):
            ordered.append(count)
        else:
            _refuse("projection_expression" if clause == "select" else "count_clause_unsupported")
        meanings[id(count)] = _meaning(root, count, aliases, fact, keys)
    output_names = [output_field_name(p) for p in root.expressions]
    if any(
        not name or len(name.encode("utf-8")) > 63 or output_names.count(name) != 1
        for name in output_names
    ):
        _refuse("count_projection_alias_ambiguous")
    metrics: list[CountMetric] = []
    for index, projection, count in sorted(selected, key=lambda item: item[0]):
        kind, column, proof = meanings[id(count)]
        name = output_names[index]
        if (
            name in {"fact_row_count", "matched_row_count"}
            and kind != CountKind.ROW_COUNT
            or name == "fact_value_count"
            and isinstance(count.this, exp.Star)
        ):
            _refuse("count_wrong_argument_semantics")
        metrics.append(
            CountMetric(
                kind,
                fact,
                column,
                name,
                index,
                proof,
                tuple((r.relationship_id, r.revision) for r in relationships),
                count.copy(),
                projection.copy(),
                tuple(e.copy() for e in root.args["group"].expressions)
                if root.args.get("group")
                else (),
            )
        )
    metric_names = {m.output_alias for m in metrics}
    for group in root.args["group"].expressions if root.args.get("group") else ():
        if (
            isinstance(group, exp.Column)
            and not group.table
            and output_field_name(group) in metric_names
            and output_field_name(group) not in (input_names or set())
            or isinstance(group, exp.Literal)
            and group.is_int
            and int(group.this) - 1 in {m.projection_index for m in metrics}
        ):
            _refuse("count_group_reference")
    replacements: list[tuple[exp.Count, CountMetric]] = []
    for count in ordered:
        kind, column, _ = meanings[id(count)]
        signature = (kind, fact, column if kind == CountKind.NON_NULL_VALUE_COUNT else None)
        matches = [m for m in metrics if m.signature == signature]
        if not matches:
            _refuse("count_order_non_equivalent" if metrics else "count_order_unprojected")
        replacements.append((count, matches[0]))
    # No AST mutation until every COUNT, output identity and sort reference is proved safe.
    if normalize:
        for index, projection, count in selected:
            if projection is count:
                projections = list(root.expressions)
                projections[index] = exp.alias_(count.copy(), "count")
                root.set("expressions", projections)
                metrics = [
                    replace(m, normalization=m.normalization + ("explicit_default_label",))
                    if m.projection_index == index
                    else m
                    for m in metrics
                ]
        for count, metric in replacements:
            record_aggregate_shape(root, count, matching=True, candidate=True, applied=True)
            projection = root.expressions[metric.projection_index]
            count.parent.set("this", exp.Column(this=projection.args["alias"].copy()))
            metrics = [
                replace(m, normalization=m.normalization + ("selected_order_reference",))
                if m.projection_index == metric.projection_index
                else m
                for m in metrics
            ]
            with suppress(Exception), diagnostic_stage("aggregate_normalization"):
                pass
    return tuple(metrics)


def count_evidence(metrics: tuple[CountMetric, ...]) -> list[dict[str, Any]]:
    """Authorized field provenance for grounding, not logs or additional API fields."""
    return [
        {
            "field": m.output_alias,
            "kind": m.kind.value,
            "source_column": m.fact_column,
            "nonnull_proof": m.non_null_proof.value,
            "scope": "matched_fact_rows" if m.relationships else "source_rows",
        }
        for m in metrics
    ]
