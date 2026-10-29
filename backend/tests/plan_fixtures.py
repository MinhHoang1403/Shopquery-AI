"""Translate static SQL regression fixtures into provider plans, never production input.

The original SQL is independently validated before translation. PostgreSQL expected rows
remain unchanged; these fixtures do not infer plans from natural-language questions.
"""

import json

from sqlglot import exp, parse_one

from app.datasets.context import DatasetSqlContext
from app.text_to_sql.join_policy import ApprovedJoin
from app.text_to_sql.query_plan import PlanDecision, PlanExpression, PlanField, PlanSort, QueryPlan
from app.text_to_sql.validator import SqlValidator


def decision_from_sql(sql: str, prompt: str) -> PlanDecision:
    if "Authorized catalog JSON:\n" in prompt:
        catalog = json.JSONDecoder().raw_decode(prompt.split("Authorized catalog JSON:\n", 1)[1])[0]
    else:
        data = json.JSONDecoder().raw_decode(prompt.split("Source/context data:\n", 1)[1])[0]
        catalog = {**data["catalog"], "joins_enabled": bool(data["catalog"]["relationships"])}
        columns_by_location = {
            (table["name"], column["name"]): column["id"]
            for table in catalog["tables"]
            for column in catalog["columns"]
            if column["id"].split(".")[0] == table["id"]
        }
        catalog["relationships"] = [
            {
                **edge,
                "source": columns_by_location[(edge["source_table"], edge["source_column"])],
                "target": columns_by_location[(edge["target_table"], edge["target_column"])],
                "revision": "scripted-approved-revision",
            }
            for edge in catalog["relationships"]
        ]
    names = {table["id"]: table["name"] for table in catalog["tables"]}
    columns = {
        column["id"]: (names[column["id"].split(".")[0]], column["name"])
        for column in catalog["columns"]
    }
    types = {name: {} for name in names.values()}
    for column in catalog["columns"]:
        table, name = columns[column["id"]]
        types[table][name] = column["type"]
    joins = tuple(
        ApprovedJoin(
            relation["id"],
            *columns[relation["source"]],
            *columns[relation["target"]],
            relation["revision"],
        )
        for relation in catalog["relationships"]
    )
    raw = parse_one(sql, read="postgres")
    schemas = {table.name: table.db or None for table in raw.find_all(exp.Table)}
    context = DatasetSqlContext(
        "",
        {name: set(cols) for name, cols in types.items()},
        {name: schemas[name] for name in types if schemas.get(name)},
        column_types=types,
        approved_joins=joins,
    )
    default = set(names.values()) == {"products", "categories", "orders", "order_items"}
    checked = SqlValidator(
        context.table_columns,
        context.allowed_schemas,
        max_tables=None if default else 3 if joins else 1,
        approved_joins=joins,
        column_types=types,
        join_v1_enabled=catalog["joins_enabled"],
    ).validate(sql)
    root = parse_one(checked.statement, read="postgres")
    bindings = {table.alias_or_name: table.name for table in root.find_all(exp.Table)}
    reverse = {value: key for key, value in columns.items()}
    nodes = []

    def node(operation, *args, **kwargs):
        nodes.append(PlanExpression(operation=operation, arguments=list(args), **kwargs))
        return f"e{len(nodes) - 1}"

    def expression(item):
        if isinstance(item, (exp.Alias, exp.Paren)):
            return expression(item.this)
        if isinstance(item, exp.Column):
            table = (
                bindings.get(item.table)
                if item.table
                else next(name for name in bindings.values() if (name, item.name) in reverse)
            )
            return reverse[(table, item.name)]
        if isinstance(item, exp.Literal):
            return node(
                "literal", value=item.this, value_type="TEXT" if item.is_string else "NUMERIC"
            )
        if isinstance(item, exp.Boolean):
            return node("literal", value=str(item.this).lower(), value_type="BOOLEAN")
        if isinstance(item, exp.Cast):
            if isinstance(item.this, exp.Literal):
                kinds = {
                    "TIMESTAMPTZ": "TIMESTAMPTZ",
                    "TIMESTAMP": "TIMESTAMP",
                    "DATE": "DATE",
                    "DECIMAL": "NUMERIC",
                    "BIGINT": "BIGINT",
                    "TEXT": "TEXT",
                }
                kind = kinds.get(item.to.this.value)
                if kind:
                    return node("literal", value=item.this.this, value_type=kind)
            return expression(item.this)
        if isinstance(item, exp.Neg):
            return node(
                "subtract", node("literal", value="0", value_type="NUMERIC"), expression(item.this)
            )
        if isinstance(item, exp.Count):
            return (
                node("row_count")
                if item.this.is_star
                else node("value_count", expression(item.this))
            )
        functions = {exp.Sum: "sum", exp.Avg: "avg", exp.Min: "min", exp.Max: "max"}
        if type(item) in functions:
            return node(functions[type(item)], expression(item.this))
        binary = {
            exp.Add: "add",
            exp.Sub: "subtract",
            exp.Mul: "multiply",
            exp.Div: "divide",
            exp.EQ: "eq",
            exp.NEQ: "ne",
            exp.GT: "gt",
            exp.GTE: "gte",
            exp.LT: "lt",
            exp.LTE: "lte",
            exp.And: "and",
            exp.Or: "or",
        }
        if type(item) in binary:
            return node(binary[type(item)], expression(item.this), expression(item.expression))
        if isinstance(item, exp.Is) and isinstance(item.expression, exp.Null):
            return node("is_null", expression(item.this))
        if isinstance(item, exp.Not) and isinstance(item.this, exp.Is):
            return node("is_not_null", expression(item.this.this))
        if isinstance(item, exp.In):
            return node(
                "in", expression(item.this), *(expression(value) for value in item.expressions)
            )
        raise AssertionError(f"Static SQL fixture needs an explicit typed plan: {item.key}")

    fields = []
    projected = {}
    for projection in root.expressions:
        if projection.is_star:
            for table in bindings.values():
                for name in sorted(types[table]):
                    fields.append(PlanField(reference=reverse[(table, name)], alias=name))
            continue
        name = projection.alias_or_name or projection.output_name
        if not name:
            name = (
                projection.this.sql_name().lower()
                if isinstance(projection, exp.Alias)
                else projection.sql_name().lower()
            )
        reference = expression(projection)
        fields.append(PlanField(reference=reference, alias=name))
        projected[name] = reference
    groups = []
    for group in root.args["group"].expressions if root.args.get("group") else []:
        if isinstance(group, exp.Column) and not group.table and group.name in projected:
            # PostgreSQL GROUP BY prefers a real input column over an output alias.
            candidates = [
                value
                for value in reverse
                if value[0] in bindings.values() and value[1] == group.name
            ]
            groups.append(reverse[candidates[0]] if candidates else projected[group.name])
        elif isinstance(group, exp.Literal) and group.is_int:
            groups.append(fields[int(group.this) - 1].reference)
        else:
            groups.append(expression(group))
    sorts = []
    for order in root.args["order"].expressions if root.args.get("order") else []:
        value = order.this
        name = value.name if isinstance(value, exp.Column) and value.name in projected else None
        if name is None:
            ref = expression(value)
            name = next((field.alias for field in fields if field.reference == ref), ref)
        sorts.append(
            PlanSort(
                field=name,
                direction="desc" if order.args.get("desc") else "asc",
                nulls="first" if order.args.get("nulls_first") else "last",
            )
        )
    where = expression(root.args["where"].this) if root.args.get("where") else None
    having = expression(root.args["having"].this) if root.args.get("having") else None
    used = set(bindings.values())
    source = root.args["from_"].this.name
    if default and len(used) > 1:
        source = next(
            iter(
                used
                - {
                    r.target_table
                    for r in joins
                    if r.source_table in used and r.target_table in used
                }
            )
        )
    return PlanDecision(
        plan=QueryPlan(
            source=next(key for key, name in names.items() if name == source),
            fields=fields,
            expressions=nodes,
            where=where,
            having=having,
            group_by=groups,
            sort=sorts,
            limit=int(root.args["limit"].expression.this) if root.args.get("limit") else None,
            relationships=[
                r.relationship_id
                for r in joins
                if r.source_table in used and r.target_table in used
            ],
        )
    )
