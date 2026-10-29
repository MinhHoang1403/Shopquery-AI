"""Separate transport/evidence outcomes from conversational authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.semantic.reference import TaskReference


class ResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["answered", "partial", "insufficient_evidence", "unsupported", "failed"]
    evidence: Literal["none", "sql_executed", "citation_validated", "classification_verified"]
    # Coverage proves represented conditions survived execution, not NLP infallibility.
    semantic_status: Literal["unverified", "coverage_verified"] = "unverified"
    premise_trust: Literal["ineligible", "reference_only", "verified_result"] = "ineligible"

    @model_validator(mode="after")
    def reference_requires_answer(self) -> "ResultEnvelope":
        if self.premise_trust == "verified_result" and (
            self.outcome != "answered"
            or self.evidence != "classification_verified"
            or self.semantic_status != "coverage_verified"
        ):
            raise ValueError("Verified premise requires complete scoped classification evidence")
        if self.premise_trust == "reference_only" and (
            self.outcome != "answered" or self.evidence == "none"
        ):
            raise ValueError("Only an evidenced answer can provide a conversation reference")
        return self


def summarize_result(
    *,
    route: str | None,
    error: str | None,
    sql: str | None,
    verification_status: str | None,
    rag_answerability_claim: str | None,
    rag_grounding_status: str | None,
    source_count: int,
    semantic_reference: TaskReference | None = None,
) -> ResultEnvelope:
    """Server derivation only; a valid citation does not attest entailment or NLP coverage."""
    if error is not None:
        return ResultEnvelope(outcome="failed", evidence="none")
    if route == "SQL" and sql:
        return ResultEnvelope(
            outcome="answered",
            evidence="sql_executed",
            premise_trust="reference_only",
            semantic_status="coverage_verified"
            if semantic_reference is not None and semantic_reference.evidence == "sql_executed"
            else "unverified",
        )
    if route == "HYBRID" and sql and source_count > 0:
        if verification_status == "verified_classification":
            return ResultEnvelope(
                outcome="answered",
                evidence="classification_verified",
                semantic_status="coverage_verified"
                if semantic_reference is not None
                and semantic_reference.evidence == "classification_verified"
                else "unverified",
                premise_trust="verified_result"
                if semantic_reference is not None
                and semantic_reference.evidence == "classification_verified"
                else "reference_only",
            )
        return ResultEnvelope(outcome="partial", evidence="sql_executed")
    if route == "RAG" and source_count > 0 and rag_grounding_status == "citation_validated":
        if rag_answerability_claim == "answered":
            return ResultEnvelope(
                outcome="answered", evidence="citation_validated", premise_trust="reference_only"
            )
        return ResultEnvelope(
            outcome="insufficient_evidence"
            if rag_answerability_claim == "insufficient_evidence"
            else "partial",
            evidence="citation_validated",
        )
    return ResultEnvelope(outcome="unsupported", evidence="none")
