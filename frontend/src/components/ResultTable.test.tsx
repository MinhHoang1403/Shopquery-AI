import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ResultTable } from "./ResponseEvidence";

describe("lossless SQL result cells", () => {
  afterEach(cleanup);

  it("renders decimal strings exactly and keeps zero distinct from null", () => {
    const values = ["12345678901234567890.12", "0.000000000000000000000002", "0.00", null, 0, 4];
    const wireRows = JSON.parse(JSON.stringify(values.map((value) => ({ amount: value }))));
    render(<ResultTable rows={wireRows} />);
    const cells = screen.getAllByRole("row").slice(1).map((row) => within(row).getByRole("cell").textContent);
    expect(cells).toEqual(["12345678901234567890.12", "0.000000000000000000000002", "0.00", "—", "0", "4"]);
  });
});
