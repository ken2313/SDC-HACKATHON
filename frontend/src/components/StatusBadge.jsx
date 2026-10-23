import { STATUS_LABELS } from "../utils/stock.js";

const STYLES = {
  in_stock: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  low_stock: "bg-amber-50 text-amber-800 ring-amber-600/30",
  out_of_stock: "bg-red-50 text-red-700 ring-red-600/20",
};

const DOTS = {
  in_stock: "bg-emerald-500",
  low_stock: "bg-amber-500",
  out_of_stock: "bg-red-500",
};

export default function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${DOTS[status]}`} />
      {STATUS_LABELS[status]}
    </span>
  );
}
