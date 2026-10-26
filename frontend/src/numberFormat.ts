export function displayNumber(value: unknown): string {
  if (typeof value === "number") return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 20 }).format(value);
  if (typeof value !== "string" || !/^-?(?:0|[1-9]\d*)\.\d+$/.test(value)) return String(value);
  const [integer, fraction] = value.split(".");
  return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${fraction}`;
}
