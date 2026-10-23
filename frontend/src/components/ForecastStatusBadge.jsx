const CONFIG = {
  order_now: { label: "Order now", style: "bg-red-50 text-red-700 ring-red-600/20", dot: "bg-red-500" },
  order_soon: { label: "Order this week", style: "bg-amber-50 text-amber-800 ring-amber-600/30", dot: "bg-amber-500" },
  on_order: { label: "On order", style: "bg-sky-50 text-sky-700 ring-sky-600/20", dot: "bg-sky-500" },
  ok: { label: "OK", style: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", dot: "bg-emerald-500" },
  no_demand: { label: "No recent use", style: "bg-slate-100 text-slate-600 ring-slate-500/20", dot: "bg-slate-400" },
  insufficient_data: { label: "Not enough data", style: "bg-slate-100 text-slate-600 ring-slate-500/20", dot: "bg-slate-300" },
};

export const FORECAST_STATUS_HELP = {
  order_now: "The order-by date is today or has passed, and nothing is on order yet.",
  order_soon: "Order within the next 7 days.",
  on_order: "It should be ordered now, and an approved order is already on its way.",
  ok: "Enough stock for more than a week plus the supplier's delivery time.",
  no_demand: "Nothing was used in the last 7 days.",
  insufficient_data: "Less than 7 days of history, so no forecast is made.",
};

export default function ForecastStatusBadge({ status }) {
  const config = CONFIG[status] ?? CONFIG.insufficient_data;
  return (
    <span
      title={FORECAST_STATUS_HELP[status]}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${config.style}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      {config.label}
    </span>
  );
}
