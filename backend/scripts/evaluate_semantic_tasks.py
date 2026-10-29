"""Bounded evaluation of the locked synthetic task set; dry-run unless --live is explicit.

No SQL execution, uploads, embeddings, fallback, repair or automatic retry. Gold is
used only after each response and never enters the proposal prompt. Output is local
synthetic evidence, not Langfuse raw-content telemetry.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.ai.providers import build_generation_gateway
from app.core.config import Settings
from app.core.diagnostics import diagnostic_request
from app.core.errors import ShopQueryError
from app.datasets.context import DatasetSqlContext
from app.routing.router import QueryRouter
from app.semantic.request import RequestIdentity, semantic_request
from app.text_to_sql.compiler import SchemaReferences
from app.text_to_sql.join_policy import ApprovedJoin
from tests.semantic_evaluation import grade_structural_dimensions, task_predicates

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/semantic_population_holdout.json"
CACHE = ROOT / ".pytest_cache"
LIMIT = 120
# Test catalog types, independent of model output or question wording.
NUMERIC = {"fee", "amount", "weight_kg", "hours"}
INTEGER = {"room_count"}
TIMESTAMP = {"started_at"}


class ProposalCapture:
    """Capture authorized synthetic DTOs locally before domain conversion.

    Never attach this data to telemetry. Capturing the already returned DTO costs
    no additional provider call and lets a conversion failure become a regression.
    """

    def __init__(self, gateway):
        self.gateway = gateway
        self.proposals = []

    def generate_structured(self, prompt, schema):
        result = self.gateway.generate_structured(prompt, schema)
        self.proposals.append(result.model_dump(mode="json"))
        return result


def catalog(name: str, description: dict) -> DatasetSqlContext:
    columns, types = {}, {}
    for declaration in description["tables"]:
        table, listed = declaration.rstrip(")").split("(", 1)
        columns[table] = set(listed.split(","))
        types[table] = {
            column: "NUMERIC"
            if column in NUMERIC
            else "BIGINT"
            if column in INTEGER
            else "TIMESTAMPTZ"
            if column in TIMESTAMP
            else "DATE"
            if column.endswith("_date")
            else "TEXT"
            for column in columns[table]
        }
    edges = []
    for index, declaration in enumerate(description["relations"]):
        match = re.fullmatch(r"(\w+)\.(\w+) -> (\w+)\.(\w+), N:1", declaration)
        if match is None:
            raise ValueError("Invalid locked synthetic catalog relationship")
        edges.append(ApprovedJoin(f"synthetic-{index}", *match.groups(), "synthetic-revision"))
    return DatasetSqlContext(
        "Synthetic evaluation metadata only. " + " ".join(description["documents"]),
        columns,
        {table: "uploaded_data" for table in columns},
        dataset_id=1,
        owner_user_id=uuid5(NAMESPACE_URL, "shopquery-semantic-benchmark/" + name),
        has_documents=bool(description["documents"]),
        approved_joins=tuple(edges),
        column_types=types,
    )


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["gemini", "inetcloud-knowledge"], required=True)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--ci-receipt", type=Path)
    parser.add_argument(
        "--diagnostic-case", help="One bounded reproduction of a recorded failed case"
    )
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    suite = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if not args.live:
        print(json.dumps({"dispatch": False, "cases": len(suite["cases"]), "source": source}))
        return 0
    if args.ci_receipt is None:
        parser.error("Live evaluation requires the verified exact-source CI receipt")
    receipt = json.loads(args.ci_receipt.read_text())
    if receipt.get("source") != source or receipt.get("postgres") != "PASS":
        parser.error("PostgreSQL gate has not passed for this exact source")
    if not 1 <= args.max_cases <= len(suite["cases"]):
        parser.error("Explicit max-cases must be between 1 and the locked suite size")
    if args.env_file is None:
        parser.error("Use an explicit private configuration; do not guess provider credentials")
    settings = Settings(_env_file=args.env_file).model_copy(
        update={
            "gemini_retry_attempts": 1,
            "inetcloud_retry_attempts": 1,
            "ai_gemini_fallback_enabled": False,
        }
    )
    if (
        settings.gemini_generation_model != "gemini-3.5-flash-lite"
        or settings.inetcloud_model != "knowledge"
    ):
        parser.error("Model differs from the authorized evaluation contract")
    ledger_path = CACHE / "core_provider_budget.json"
    ledger = (
        json.loads(ledger_path.read_text())
        if ledger_path.exists()
        else {
            "generation": 0,
            "query_embeddings": 0,
            "document_embeddings": 0,
            "dispatches": [],
        }
    )
    if (
        type(ledger.get("generation")) is not int
        or not 0 <= ledger["generation"] <= LIMIT
        or ledger.get("query_embeddings") != 0
        or ledger.get("document_embeddings") != 0
    ):
        parser.error("Budget ledger requires reconciliation before dispatch")
    output_path = CACHE / f"semantic_evaluation_{args.provider}.json"
    evidence = json.loads(output_path.read_text()) if output_path.exists() else {"runs": []}
    cases = suite["cases"][: args.max_cases]
    if args.diagnostic_case:
        cases = [case for case in cases if case["id"] == args.diagnostic_case]
        if len(cases) != 1 or not any(
            run["case"] == args.diagnostic_case and run.get("error") for run in evidence["runs"]
        ):
            parser.error("Diagnostic requires one previously recorded failed synthetic case")
    gateway = build_generation_gateway(settings, args.provider)
    try:
        for case in cases:
            key = (
                args.provider
                + (":diagnostic:" if args.diagnostic_case else ":population:")
                + case["id"]
            )
            if key in ledger["dispatches"]:
                parser.error("Case already dispatched; no automatic repeat of closed evaluations")
            if ledger["generation"] >= LIMIT:
                parser.error("Cumulative generation budget exhausted")
            selected = catalog(case["context"], suite["contexts"][case["context"]])
            # Reserve before dispatch: failures and interruption still consume a slot.
            ledger["generation"] += 1
            ledger["dispatches"].append(key)
            save(ledger_path, ledger)
            start = perf_counter()
            result = {"case": case["id"], "provider": args.provider, "source": source}
            capture = ProposalCapture(gateway)
            try:
                with (
                    diagnostic_request() as trace,
                    semantic_request(
                        RequestIdentity(
                            selected.owner_user_id,
                            None,
                            1,
                            case["question"],
                            "2026-10-29",
                        )
                    ),
                ):
                    decision = QueryRouter(capture, context=selected).route(case["question"])
                result.update(
                    synthetic_proposals=capture.proposals,
                    diagnostic=bool(args.diagnostic_case),
                    task=decision.task.model_dump(mode="json"),
                    route=decision.route,
                    dimensions=grade_structural_dimensions(
                        decision.task, decision.route, case["gold"]
                    ),
                    predicates=task_predicates(
                        decision.task, SchemaReferences.from_context(selected)
                    ),
                )
            except ShopQueryError as exc:
                result["error"] = exc.error_context.model_dump(exclude_none=True)
            finally:
                result.update(
                    latency_ms=round((perf_counter() - start) * 1000),
                    usage={
                        key: trace.facts.get(key)
                        for key in ("input_tokens", "output_tokens", "total_tokens")
                    },
                    correlation_id=trace.correlation_id,
                )
                evidence["runs"].append(result)
                save(output_path, evidence)
                print(
                    json.dumps(
                        {
                            "case": result["case"],
                            "error": result.get("error"),
                            "generation_reserved": ledger["generation"],
                        }
                    )
                )
            if result.get("error"):
                return 2
    finally:
        gateway.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
