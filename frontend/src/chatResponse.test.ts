import { describe, expect, it } from "vitest";
import { parseChatResponse } from "./api";

const response = { answer: "Synthetic", route: "SQL", sql: "SELECT 1", rows: [{ total: "0.00" }], sources: [], error: null };

describe("chat runtime metadata contract", () => {
  it.each([
    { result_columns: "invalid" },
    { result_columns: [{ key: "total", label: "Total", numeric: "true" }] },
    { result_columns: [{ key: "total", label: "Total", numeric: true, provenance: "model_verified" }] },
    { verification_status: "invented" },
    { answer_row_indices: [1] },
    { answer_row_indices: [-1] },
    { answer_row_indices: [0, 0] },
    { answer_row_indices: [0.5] },
    { rag_answerability_claim: "certain" },
    { rag_grounding_status: "semantically_verified" },
    { result_envelope: { outcome: "answered", evidence: "citation_validated", semantic_status: "verified", premise_trust: "verified_result" } },
    { result_envelope: { outcome: "failed", evidence: "none", semantic_status: "unverified", premise_trust: "reference_only" } },
  ])("rejects malformed metadata %j", (fields) => {
    expect(() => parseChatResponse({ ...response, ...fields })).toThrow("không đúng định dạng");
  });
  it("accepts legacy payload and exact typed metadata", () => {
    expect(parseChatResponse(response).rows).toEqual([{ total: "0.00" }]);
    const typed = { ...response, result_columns: [{ key: "total", label: "Total", numeric: true, data_type: "NUMERIC", provenance: "aggregate", aggregate: "sum" }], answer_row_indices: [], verification_status: "unverified" };
    expect(parseChatResponse(typed)).toEqual(typed);
  });
});

it("accepts verified classification evidence and rejects incompatible premise states", () => {
  const result = { ...response, route: "HYBRID", verification_status: "verified_classification", result_envelope: { outcome: "answered", evidence: "classification_verified", semantic_status: "coverage_verified", premise_trust: "verified_result" } };
  expect(parseChatResponse(result).result_envelope?.premise_trust).toBe("verified_result");
  for (const evidence of ["none", "sql_executed", "citation_validated"]) {
    expect(() => parseChatResponse({ ...result, result_envelope: { ...result.result_envelope, evidence } })).toThrow();
  }
});
