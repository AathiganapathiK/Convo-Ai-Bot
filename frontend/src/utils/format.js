export const CURRENCY_COLUMNS = [
  "sales",
  "totalsales",
  "revenue",
  "amount",
  "cost",
  "totalcost",
  "profit",
  "price",
  "unitprice",
  "discount",
  "discountamount",
  "marginvalue",
  "target"
];

export const isCurrencyColumn = (columnName = "") => {
  const normalized = columnName
    .replace(/[_\s]/g, "")
    .toLowerCase();

  return CURRENCY_COLUMNS.includes(normalized);
};

export const isPercentageColumn = (columnName = "") => {
  const lower = columnName.toLowerCase();

  return (
    lower.includes("margin") ||
    lower.includes("percent") ||
    lower.includes("percentage") ||
    lower.includes("rate") ||
    lower.includes("ratio") ||
    lower.includes("pct")
  );
};

export const formatIndianCurrency = (value) => {
  if (value === null || value === undefined) return "";

  const num = Number(value);

  if (Number.isNaN(num)) return value;

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(num);
};

export const formatNumber = (value) => {
  if (value === null || value === undefined) return "";

  const num = Number(value);

  if (Number.isNaN(num)) return value;

  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 2,
  }).format(num);
};

export const formatValue = (value, columnName = "") => {
  if (value === null || value === undefined) return "";

  if (typeof value !== "number") return value;

  if (isPercentageColumn(columnName)) {
    const pct = value > 0 && value < 1 ? value * 100 : value;
    return `${pct.toFixed(1)}%`;
  }

  if (isCurrencyColumn(columnName)) {
    return formatIndianCurrency(value);
  }

  return formatNumber(value);
};

export const getAxisLabel = (labelName, isYAxis = false) => {
  if (!labelName) return "";

  const cleanLabel = labelName
    .replace(/_/g, " ")
    .replace(/^Total\s*/i, "")
    .trim();

  let unit = "";

  if (isCurrencyColumn(labelName)) {
    unit = " (₹)";
  } else if (isPercentageColumn(labelName)) {
    unit = " (%)";
  } else {
    const lower = labelName.toLowerCase();

    if (
      lower.includes("qty") ||
      lower.includes("quantity") ||
      lower.includes("count")
    ) {
      unit = " (Units)";
    }
  }

  return `${cleanLabel}${unit}`;
};

export const formatAxisValue = (value, columnName = "") => {
  if (value === null || value === undefined) return "";

  const num = Number(value);
  if (Number.isNaN(num)) return value;

  if (isPercentageColumn(columnName)) {
    const pct = num > 0 && num < 1 ? num * 100 : num;
    return `${pct.toFixed(1)}%`;
  }

  const isCurr = isCurrencyColumn(columnName);
  const prefix = isCurr ? "₹" : "";
  const absNum = Math.abs(num);
  const sign = num < 0 ? "-" : "";

  if (absNum === 0) {
    return `${prefix}0`;
  }

  if (absNum >= 10000000) {
    const val = absNum / 10000000;
    const formatted = val % 1 === 0 ? val.toString() : val.toFixed(2).replace(/\.?0+$/, "");
    return `${sign}${prefix}${formatted} Cr`;
  }

  if (absNum >= 100000) {
    const val = absNum / 100000;
    const formatted = val % 1 === 0 ? val.toString() : val.toFixed(2).replace(/\.?0+$/, "");
    return `${sign}${prefix}${formatted} L`;
  }

  if (absNum >= 1000) {
    const val = absNum / 1000;
    const formatted = val % 1 === 0 ? val.toString() : val.toFixed(2).replace(/\.?0+$/, "");
    return `${sign}${prefix}${formatted} K`;
  }

  if (isCurr) {
    return `${sign}${prefix}${absNum.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  }

  return formatNumber(num);
};