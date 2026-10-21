// Mirrors the backend rule so the form can preview the result.
// The BACKEND is still the source of truth: it recalculates the status itself.
export function computeStatus(quantity, threshold) {
  if (quantity <= 0) return "out_of_stock";
  if (quantity <= threshold) return "low_stock";
  return "in_stock";
}

export const STATUS_LABELS = {
  in_stock: "In Stock",
  low_stock: "Low Stock",
  out_of_stock: "Out of Stock",
};

export function newRequestId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function formatDateTime(isoText) {
  if (!isoText) return "";
  const date = new Date(isoText);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("en-MY", { dateStyle: "medium", timeStyle: "short" });
}

export function isWholeNumber(text) {
  return /^\d+$/.test(String(text).trim());
}
