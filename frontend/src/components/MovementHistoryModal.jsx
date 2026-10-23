import { useEffect, useState } from "react";
import { inventoryApi } from "../api/inventory.js";
import { formatDateTime } from "../utils/stock.js";
import Modal from "./Modal.jsx";
import Spinner from "./Spinner.jsx";

const TYPE_LABELS = { initial: "Opening stock", in: "Stock added", out: "Stock removed" };

export default function MovementHistoryModal({ item, onClose }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    inventoryApi
      .movements(item.id)
      .then((data) => !cancelled && setRows(data))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [item.id]);

  return (
    <Modal title="Stock history" subtitle={`${item.name} · ${item.sku}`} onClose={onClose} size="lg">
      {error && <p className="text-sm text-red-600">{error}</p>}
      {!rows && !error && <Spinner label="Loading history…" />}
      {rows && rows.length === 0 && <p className="py-6 text-center text-sm text-slate-500">No stock changes recorded yet.</p>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-4 font-medium">When</th>
                <th className="py-2 pr-4 font-medium">Type</th>
                <th className="py-2 pr-4 text-right font-medium">Change</th>
                <th className="py-2 pr-4 text-right font-medium">Before → After</th>
                <th className="py-2 pr-4 font-medium">By</th>
                <th className="py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="whitespace-nowrap py-2 pr-4 text-slate-600">{formatDateTime(row.created_at)}</td>
                  <td className="whitespace-nowrap py-2 pr-4">{TYPE_LABELS[row.movement_type] ?? row.movement_type}</td>
                  <td
                    className={`whitespace-nowrap py-2 pr-4 text-right font-semibold ${
                      row.quantity_change > 0 ? "text-emerald-600" : "text-red-600"
                    }`}
                  >
                    {row.quantity_change > 0 ? "+" : ""}
                    {row.quantity_change}
                  </td>
                  <td className="whitespace-nowrap py-2 pr-4 text-right text-slate-600">
                    {row.quantity_before} → {row.quantity_after}
                  </td>
                  <td className="whitespace-nowrap py-2 pr-4 text-slate-600">{row.user_name ?? "—"}</td>
                  <td className="py-2 text-slate-600">{row.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
