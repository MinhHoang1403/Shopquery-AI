"""Grade task proposals against locked evaluation gold, never against another provider."""

from app.semantic.task import Predicate, PredicateGroup, SemanticTask
from app.text_to_sql.compiler import SchemaReferences


def task_population(task: SemanticTask) -> str:
    if task.operation != "apply_policy":
        return "not_applicable"
    return "filtered_entities" if task.population.predicates is not None else "all_entities"


def task_predicates(task: SemanticTask, references: SchemaReferences) -> list[dict]:
    def leaves(node):
        if node is None:
            return []
        if isinstance(node, PredicateGroup):
            return [
                {
                    "boolean": node.kind,
                    "children": [leaf for child in node.children for leaf in leaves(child)],
                }
            ]
        assert isinstance(node, Predicate)
        return [
            {
                "source": references.columns.get(node.reference),
                "operator": node.operator,
                "values": [v.model_dump() for v in node.values],
                "reference": node.reference,
            }
        ]

    return leaves(task.population.predicates) if task.population else []


def grade_structural_dimensions(task: SemanticTask, route: str, gold: dict) -> dict:
    """Only grade dimensions that the gold explicitly defines.

    Qualifier entailment requires independent inspection/execution; those dimensions
    remain UNKNOWN here rather than being declared PASS from a correct route label.
    """
    operation = {
        "apply": "apply_policy",
        "query": "query",
        "explain": "explain",
        "clarify": "clarify",
    }
    result = {"task": task.operation == operation[gold["task"]], "route": route == gold["route"]}
    if gold["population"] not in {"unknown", "not_applicable"}:
        result["population"] = task_population(task) == gold["population"]
    if gold["selection"] not in {"unknown", "not_applicable"}:
        result["selection"] = (
            task.output is not None and task.output.classification == gold["selection"]
        )
    result["input_qualifiers"] = (
        "UNKNOWN"
        if gold["input_qualifiers"]
        else not (task.population is not None and task.population.predicates is not None)
    )
    result["output_qualifiers"] = (
        "UNKNOWN"
        if gold["output_qualifiers"]
        else not (
            task.output is not None
            and (task.output.ordering or task.output.limit or task.output.predicates)
        )
    )
    result["false_refusal"] = gold["route"] != "UNSUPPORTED" and route == "UNSUPPORTED"
    result["execution_correctness"] = "NOT_EVALUATED"
    return result
