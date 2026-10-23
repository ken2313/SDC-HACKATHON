const STYLES = {
  approved: ["bg-emerald-50 text-emerald-700 ring-emerald-600/20", "Approved"],
  rejected: ["bg-red-50 text-red-700 ring-red-600/20", "Rejected"],
  denied: ["bg-amber-50 text-amber-800 ring-amber-600/30", "Blocked"],
};

export default function ApprovalBadge({ status }) {
  if (!status || !STYLES[status]) return <span className="text-slate-300">–</span>;
  const [classes, label] = STYLES[status];
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${classes}`}>
      {label}
    </span>
  );
}
