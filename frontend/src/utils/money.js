// Money is shown in Malaysian Ringgit. The backend sends plain numbers in RM (for example 117.5).
const rmFormatter = new Intl.NumberFormat("en-MY", { style: "currency", currency: "MYR" });

export function formatRM(amount) {
  if (amount === null || amount === undefined || Number.isNaN(Number(amount))) return "–";
  return rmFormatter.format(Number(amount));
}

// Dates without a time ("2026-10-23") are shown as written, with no time-zone shifting.
export function formatDateOnly(isoDate) {
  if (!isoDate) return "–";
  const [year, month, day] = String(isoDate).split("-").map(Number);
  if (!year || !month || !day) return "–";
  return new Date(year, month - 1, day).toLocaleDateString("en-MY", { dateStyle: "medium" });
}
