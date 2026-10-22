const CONFIG = {
  critical: { label: "Critical", style: "bg-red-50 text-red-700 ring-red-600/20", dot: "bg-red-500" },
  urgent: { label: "Urgent", style: "bg-orange-50 text-orange-700 ring-orange-600/25", dot: "bg-orange-500" },
  low: { label: "Low", style: "bg-amber-50 text-amber-800 ring-amber-600/30", dot: "bg-amber-500" },
};

export const URGENCY_HELP = {
  critical: "Out of stock",
  urgent: "Half of the reorder level or less is left",
  low: "At or below the reorder level",
};

export default function UrgencyBadge({ urgency }) {
  const config = CONFIG[urgency];
  if (!config) return <span className="text-slate-400">—</span>;
  return (
    <span
      title={URGENCY_HELP[urgency]}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${config.style}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      {config.label}
    </span>
  );
}
