export const formatNumber = (value) => {
  if (value === null || value === undefined) return "";
  const num = Number(value);
  if (isNaN(num)) return value;
  return new Intl.NumberFormat(
    "en-US",
    {
      notation: "compact",
      maximumFractionDigits: 2
    }
  ).format(num);
};

export const getAxisLabel = (labelName, isYAxis = false) => {
  if (!labelName) return "";
  
  const cleanLabel = labelName
    .replace(/_/g, " ")
    .replace(/^Total\s*/i, "")
    .trim();

  let unit = "";
  const lower = labelName.toLowerCase();
  if (lower.includes("sales") || lower.includes("cost") || lower.includes("price") || lower.includes("revenue") || lower.includes("profit") || lower.includes("amount")) {
    unit = " ($)";
  } else if (lower.includes("pct") || lower.includes("percent") || lower.includes("rate") || lower.includes("margin")) {
    unit = " (%)";
  } else if (lower.includes("qty") || lower.includes("quantity") || lower.includes("count")) {
    unit = " (units)";
  }

  if (isYAxis) {
    return `${cleanLabel} →${unit}`;
  } else {
    return `${cleanLabel} →${unit}`;
  }
};
