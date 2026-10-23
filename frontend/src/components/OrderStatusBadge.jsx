const CONFIG = {
  draft: { label: "Draft", style: "bg-slate-100 text-slate-700 ring-slate-500/20", dot: "bg-slate-400" },
  pending_approval: { label: "Pending approval", style: "bg-amber-50 text-amber-800 ring-amber-600/30", dot: "bg-amber-500" },
  approved: { label: "Approved", style: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", dot: "bg-emerald-500" },
  ordered: { label: "Ordered", style: "bg-sky-50 text-sky-700 ring-sky-600/20", dot: "bg-sky-500" },
  shipped: { label: "Shipped", style: "bg-indigo-50 text-indigo-700 ring-indigo-600/20", dot: "bg-indigo-500" },
  delivered: { label: "Delivered", style: "bg-emerald-50 text-emerald-800 ring-emerald-700/20", dot: "bg-emerald-600" },
  delayed: { label: "Delayed", style: "bg-orange-50 text-orange-700 ring-orange-600/25", dot: "bg-orange-500" },
  cancelled: { label: "Cancelled", style: "bg-slate-100 text-slate-600 ring-slate-500/20", dot: "bg-slate-400" },
  rejected: { label: "Rejected", style: "bg-red-50 text-red-700 ring-red-600/20", dot: "bg-red-500" },
};

export default function OrderStatusBadge({ status }) {
  const config = CONFIG[status] ?? { label: status, style: "bg-slate-100 text-slate-700 ring-slate-500/20", dot: "bg-slate-400" };
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${config.style}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      {config.label}
    </span>
  );
}
