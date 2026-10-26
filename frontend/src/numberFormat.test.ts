import { describe, expect, it } from "vitest";
import { displayNumber } from "./numberFormat";

describe("lossless number display", () => {
  it("formats exact decimal strings without converting through Number", () => {
    expect(displayNumber("638885507.75")).toBe("638.885.507,75");
    expect(displayNumber("9007199254740993.0000")).toBe("9.007.199.254.740.993,0000");
    expect(displayNumber("0.0000")).toBe("0,0000");
    expect(displayNumber("-1200.50")).toBe("-1.200,50");
    expect(displayNumber("00123")).toBe("00123");
    expect(displayNumber("TS01")).toBe("TS01");
    expect(displayNumber(2400)).toBe("2.400");
  });
});
