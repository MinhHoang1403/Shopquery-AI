export function displayNumber(value: unknown, integerStrings = false): string {
  if (typeof value === "number") return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 20 }).format(value);
  if (typeof value !== "string") return String(value);
  if (integerStrings && /^-?(?:0|[1-9]\d*)$/.test(value)) return value.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  if (!/^-?(?:0|[1-9]\d*)\.\d+$/.test(value)) return value;
  const [integer, fraction] = value.split(".");
  return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${fraction}`;
}
