"""One semantic COUNT matrix shared by unit and PostgreSQL conformance tests."""

from dataclasses import dataclass

from sqlglot import exp, parse_one


@dataclass(frozen=True)
class CountCase:
    name: str
    projections: tuple[tuple[str, str | None, str], ...]
    ordering: tuple[str, ...] = ()
    min_tables: int = 1


POSITIVE_COUNTS = (
    CountCase("canonical_rows", (("COUNT(*)", "fact_row_count", "rows"),)),
    CountCase("business_rows", (("COUNT(*)", "delivery_count", "rows"),), ("delivery_count DESC",)),
    CountCase("ascii_case_rows", (("COUNT(*)", "EVENT_COUNT", "rows"),), ("EVENT_COUNT ASC",)),
    CountCase("utf8_rows", (("COUNT(*)", "Đếm", "rows"),), ("Đếm DESC",)),
    CountCase(
        "utf8_distinct_labels",
        (
            ("COUNT(*)", "Đếm", "rows"),
            ("COUNT(f.{measure})", "đếm", "values"),
        ),
        ("Đếm DESC", "đếm ASC"),
    ),
    CountCase("bare_rows", (("COUNT(*)", None, "rows"),), ("COUNT(*) ASC",)),
    CountCase(
        "quoted_rows",
        (("COUNT(*)", '"total_events"', "rows"),),
        ('"total_events" DESC NULLS LAST',),
    ),
    CountCase("key_business", (("COUNT(f.{key})", "key_count", "key"),), ("key_count ASC",)),
    CountCase("key_rows", (("COUNT(f.{key})", "fact_row_count", "key"),), ("COUNT(*) DESC",), 2),
    CountCase("canonical_values", (("COUNT(f.{measure})", "fact_value_count", "values"),)),
    CountCase(
        "business_values",
        (("COUNT(f.{measure})", "present_values", "values"),),
        ("COUNT(f.{measure}) DESC",),
    ),
    CountCase(
        "star_key_order",
        (("COUNT(*)", "orders_total", "rows"),),
        ("COUNT(f.{key}) DESC NULLS FIRST",),
        2,
    ),
    CountCase(
        "key_star_order",
        (("COUNT(f.{key})", "paid_events", "key"),),
        ("COUNT(*) ASC NULLS LAST",),
        2,
    ),
    CountCase("source_name_shadow", (("COUNT(*)", "{measure}", "rows"),), ("{measure} DESC",)),
    CountCase(
        "multiple_metrics",
        (
            ("COUNT(*)", "event_count", "rows"),
            ("COUNT(f.{measure})", "present_count", "values"),
        ),
        ("COUNT(*) DESC", "COUNT(f.{measure}) ASC NULLS FIRST"),
    ),
    CountCase(
        "equivalent_projections",
        (
            ("COUNT(*)", "rows_first", "rows"),
            ("COUNT(*)", "rows_second", "rows"),
        ),
        ("COUNT(*) DESC",),
    ),
)


def selections(case: CountCase, key: str, measure: str) -> list[str]:
    return [
        expression.format(key=key, measure=measure)
        + (" AS " + alias.format(measure=measure) if alias else "")
        for expression, alias, _ in case.projections
    ]


def output_names(case: CountCase, measure: str) -> list[str]:
    names = []
    for _, alias, _ in case.projections:
        name = alias.format(measure=measure) if alias else "count"
        names.append(
            name.strip('"')
            if name.startswith('"')
            else name.translate(
                str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
            )
        )
    return names


@dataclass(frozen=True)
class UnsafeCountCase:
    name: str
    projection: str | None = None
    suffix: str = ""
    reason: str | None = None
    mutation: str | None = None


UNSAFE_COUNTS = (
    UnsafeCountCase(
        "nullable_as_rows",
        "COUNT(f.{measure}) AS fact_row_count",
        reason="count_wrong_argument_semantics",
    ),
    UnsafeCountCase(
        "arbitrary_id_as_rows",
        "COUNT(f.{id}) AS fact_row_count",
        reason="count_wrong_argument_semantics",
    ),
    UnsafeCountCase("dimension", "COUNT(d.{key}) AS event_count", reason="dimension_column"),
    UnsafeCountCase(
        "distinct", "COUNT(DISTINCT f.{key}) AS event_count", reason="argument_expression"
    ),
    UnsafeCountCase(
        "filter", "COUNT(*) FILTER(WHERE f.{measure}>0) AS event_count", reason="filter"
    ),
    UnsafeCountCase("arithmetic", "COUNT(*)+1 AS event_count", reason="projection_expression"),
    UnsafeCountCase(
        "nested", "COALESCE(COUNT(*),0) AS event_count", reason="projection_expression"
    ),
    UnsafeCountCase(
        "nullable_argument_nested",
        "COUNT(COALESCE(f.{measure},0)) AS event_count",
        reason="argument_expression",
    ),
    UnsafeCountCase(
        "unprojected_order", mutation="unprojected_order", reason="count_order_unprojected"
    ),
    UnsafeCountCase(
        "different_order",
        "COUNT(f.{measure}) AS present_count",
        mutation="different_order",
        reason="count_order_non_equivalent",
    ),
    UnsafeCountCase(
        "having", "COUNT(*) AS event_count", mutation="having", reason="count_having_unsupported"
    ),
    UnsafeCountCase(
        "group_metric",
        "COUNT(*) AS event_count",
        mutation="group_metric",
        reason="count_group_reference",
    ),
    UnsafeCountCase(
        "duplicate_alias", "COUNT(*) AS total", reason="count_projection_alias_ambiguous"
    ),
    UnsafeCountCase(
        "duplicate_bare", "COUNT(*),COUNT(f.{measure})", reason="count_projection_alias_ambiguous"
    ),
    UnsafeCountCase("wrong_key", "COUNT(*) AS event_count", mutation="wrong_key"),
    UnsafeCountCase("wrong_grain", "COUNT(*) AS event_count", mutation="wrong_grain"),
    UnsafeCountCase("dml", mutation="dml"),
    UnsafeCountCase("catalog", mutation="catalog"),
    UnsafeCountCase("window", "COUNT(*) OVER() AS event_count"),
    UnsafeCountCase("unsafe_function", "pg_sleep(1) AS event_count"),
)


def unsafe_query(
    base: str, case: UnsafeCountCase, *, key: str, measure: str, identifier: str
) -> str:
    root = parse_one(base, read="postgres")
    expressions = root.expressions[:-2]
    if case.projection:
        template = case.projection.format(key=key, measure=measure, id=identifier)
        expressions += parse_one("SELECT " + template, read="postgres").expressions
    root.set("expressions", expressions)
    root.set("order", exp.Order(expressions=[exp.Ordered(this=exp.column("entity_id"))]))
    if case.mutation in {"unprojected_order", "different_order"}:
        root.set("order", parse_one("SELECT 1 ORDER BY COUNT(*)", read="postgres").args["order"])
    elif case.mutation == "having":
        root.set("having", parse_one("SELECT 1 HAVING COUNT(*)>0", read="postgres").args["having"])
    elif case.mutation == "group_metric":
        root.args["group"].append("expressions", exp.column("event_count"))
    elif case.mutation == "wrong_key":
        root.args["joins"][0].args["on"].set("this", exp.column(identifier, table="f"))
    elif case.mutation == "wrong_grain":
        root.set("expressions", [e for e in root.expressions if e.alias != "entity_id"])
        root.set("group", exp.Group(expressions=root.args["group"].expressions[1:]))
        root.set("order", None)
    elif case.mutation == "dml":
        return "DELETE FROM " + root.args["from_"].this.sql(dialect="postgres")
    elif case.mutation == "catalog":
        return "SELECT * FROM pg_catalog.pg_tables"
    return root.sql(dialect="postgres")
