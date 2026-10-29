"""Evaluation dimensions cannot promote JSON/routing success to semantic correctness."""

from tests.semantic_evaluation import grade_structural_dimensions
from tests.semantic_fixtures import proposal_for_evidence


def test_policy_oracle_checks_values_and_post_verification_order_independently():
    import pytest

    from tests.semantic_fixtures import assert_policy_rows

    expected = [{"id": "A", "metric": "0.00"}, {"id": "B", "metric": None}]
    evidence = list(reversed(expected))
    assert_policy_rows(evidence, expected, "id", (1, 0))
    with pytest.raises(AssertionError):
        assert_policy_rows(evidence, expected, "id", (0, 1))
    with pytest.raises(AssertionError):
        assert_policy_rows([{"id": "A", "metric": None}, expected[1]], expected, "id")


def gold(**changes):
    return {
        "task": "apply",
        "route": "HYBRID",
        "population": "all_entities",
        "selection": "qualified",
        "input_qualifiers": [],
        "output_qualifiers": [],
        **changes,
    }


def test_route_success_does_not_grade_unchecked_qualifiers_or_execution_as_pass():
    task = proposal_for_evidence("both", "qualified").task("Assess the selected units.")
    dimensions = grade_structural_dimensions(
        task, "HYBRID", gold(input_qualifiers=["entities.region = North"])
    )
    assert dimensions["route"] is True
    assert dimensions["input_qualifiers"] == "UNKNOWN"
    assert dimensions["execution_correctness"] == "NOT_EVALUATED"


def test_valid_question_refusal_is_not_success_even_if_backend_is_safe():
    task = proposal_for_evidence("unavailable").task("Assess the selected units.")
    dimensions = grade_structural_dimensions(task, "UNSUPPORTED", gold())
    assert dimensions["false_refusal"] is True and dimensions["task"] is False


def test_output_selection_is_graded_independently_from_population():
    task = proposal_for_evidence("both", "not_qualified").task("Assess the selected units.")
    dimensions = grade_structural_dimensions(task, "HYBRID", gold())
    assert dimensions["population"] is True and dimensions["selection"] is False
