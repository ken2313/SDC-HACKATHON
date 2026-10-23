import ApprovalBadge from "./ApprovalBadge.jsx";
import Modal from "./Modal.jsx";
import { formatDateTime } from "../utils/stock.js";

export function formatValue(value) {
  if (value === null || value === undefined) return "–";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function prettyField(name) {
  return name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export default function LogDetailModal({ entry, onClose }) {
  return (
    <Modal title={entry.action_label} subtitle={formatDateTime(entry.created_at)} onClose={onClose} size="lg">
      <p className="text-sm text-slate-700">{entry.summary}</p>

      <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">User</dt>
          <dd className="text-slate-900">
            {entry.user_name}
            {entry.user_role && <span className="ml-1 text-slate-500">({entry.user_role})</span>}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Affected record</dt>
          <dd className="text-slate-900">
            {entry.entity_label ?? "–"}
            <span className="ml-1 text-slate-500">
              ({entry.entity_type}
              {entry.entity_id != null ? ` #${entry.entity_id}` : ""})
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Action code</dt>
          <dd className="font-mono text-xs text-slate-700">{entry.action}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Approval status</dt>
          <dd>
            <ApprovalBadge status={entry.approval_status} />
          </dd>
        </div>
      </dl>

      <h3 className="mt-5 text-sm font-semibold text-slate-900">Previous and updated values</h3>
      {entry.changes.length === 0 ? (
        <p className="mt-1 text-sm text-slate-500">No values were recorded for this entry.</p>
      ) : (
        <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Field</th>
                <th className="px-3 py-2 font-medium">Previous</th>
                <th className="px-3 py-2 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody>
              {entry.changes.map((change) => (
                <tr key={change.field} className="border-t border-slate-100 align-top">
                  <td className="px-3 py-2 text-slate-600">{prettyField(change.field)}</td>
                  <td className="break-words px-3 py-2 text-red-700">{formatValue(change.old)}</td>
                  <td className="break-words px-3 py-2 text-emerald-700">{formatValue(change.new)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-4 text-xs text-slate-400">Log entries are read-only. They cannot be edited or deleted.</p>
    </Modal>
  );
}
