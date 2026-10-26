import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ResultTable } from "./ResponseEvidence";

describe("lossless SQL result cells", () => {
  afterEach(cleanup);

  it("renders decimal strings exactly and keeps zero distinct from null", () => {
    const values = ["12345678901234567890.12", "0.000000000000000000000002", "0.00", null, 0, 4, "9007199254740993"];
    const wireRows = JSON.parse(JSON.stringify(values.map((value) => ({ amount: value }))));
    render(<ResultTable rows={wireRows} />);
    const cells = screen.getAllByRole("row").slice(1).map((row) => within(row).getByRole("cell").textContent);
    expect(cells).toEqual(["12.345.678.901.234.567.890,12", "0,000000000000000000000002", "0,00", "—", "0", "4", "9007199254740993"]);
  });

  it("preserves business COUNT labels and row/value counts after a history wire roundtrip", () => {
    const rows = [{ entity_id: "A", delivery_count: 7, present_values: 4, Đếm: 0, total: "0.00" }];
    const { rerender } = render(<ResultTable rows={rows} />);
    const labels = () => screen.getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(labels()).toEqual(["entity_id", "delivery_count", "present_values", "Đếm", "total"]);
    rerender(<ResultTable rows={JSON.parse(JSON.stringify(rows))} />);
    expect(labels()).toEqual(["entity_id", "delivery_count", "present_values", "Đếm", "total"]);
    const cells = within(screen.getAllByRole("row")[1]).getAllByRole("cell");
    expect(cells.map((cell) => cell.textContent)).toEqual(["A", "7", "4", "0", "0,00"]);
    expect(rows[0].total).toBe("0.00");
    expect(rows[0].delivery_count).toBe(7);
    expect(rows[0].present_values).toBe(4);
  });
});
