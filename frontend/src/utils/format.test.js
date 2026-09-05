import { formatIndianCurrency, formatValue, formatAxisValue, isCurrencyColumn, getAxisLabel } from "./format";

describe("format.js utilities", () => {
  test("isCurrencyColumn identifies currency columns correctly", () => {
    expect(isCurrencyColumn("sales")).toBe(true);
    expect(isCurrencyColumn("Total_Sales")).toBe(true);
    expect(isCurrencyColumn("revenue")).toBe(true);
    expect(isCurrencyColumn("InvMonth")).toBe(false);
  });

  test("formatIndianCurrency formats currency correctly", () => {
    expect(formatIndianCurrency(0)).toContain("0.00");
    expect(formatIndianCurrency(10000000)).toContain("1,00,00,000.00");
  });

  test("formatAxisValue formats compact Indian numbers for chart axes", () => {
    expect(formatAxisValue(10000000, "sales")).toBe("₹1 Cr");
    expect(formatAxisValue(5000000, "sales")).toBe("₹50 L");
    expect(formatAxisValue(100000, "sales")).toBe("₹1 L");
    expect(formatAxisValue(15000, "sales")).toBe("₹15 K");
    expect(formatAxisValue(0, "sales")).toBe("₹0");
    expect(formatAxisValue(500, "sales")).toBe("₹500");
    expect(formatAxisValue(1000000, "quantity")).toBe("10 L");
  });

  test("getAxisLabel appends appropriate unit", () => {
    expect(getAxisLabel("sales", true)).toBe("sales (₹)");
    expect(getAxisLabel("InvMonth", false)).toBe("InvMonth");
  });
});
