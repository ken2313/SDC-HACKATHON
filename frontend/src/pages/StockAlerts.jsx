import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { alertsApi } from "../api/alerts.js";
import Spinner from "../components/Spinner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import StockMovementModal from "../components/StockMovementModal.jsx";
import ThresholdModal from "../components/ThresholdModal.jsx";
import UrgencyBadge, { URGENCY_HELP } from "../components/UrgencyBadge.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { formatDateTime } from "../utils/stock.js";

const PERM_MANAGE = "inventory:manage";
const PERM_STOCK = "stock:record";

const RESOLUTION_LABELS = {
  replenished: "Stock replenished",
  threshold_changed: "Reorder level changed",
  archived: "Product archived",
};

function SummaryCard({ label, value, tone, hint }) {
  const tones = { neutral: "text-slate-900", red: "text-red-600", orange: "text-orange-600", amber: "text-amber-600", green: "text-emerald-600" };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" title={hint}>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tones[tone]}`}>{value ?? "–"}</p>
    </div>
  );
}

function RowButton({ onClick, children, primary = false }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-xs font-medium ${
        primary ? "bg-indigo-600 text-white hover:bg-indigo-700" : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {children}
    </button>
  );
}

export default function StockAlerts() {
  const { can, business } = useSession();
  const toast = useToast();

  const [view, setView] = useState("open"); // "open" | "resolved"
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [stockTarget, setStockTarget] = useState(null);
  const [thresholdTarget, setThresholdTarget] = useState(null);

  // Only the newest request is allowed to update the screen
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    const requestNumber = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const [list, counts] = await Promise.all([alertsApi.list(view), alertsApi.summary()]);
      if (requestNumber !== latestRequest.current) return;
      setRows(list);
      setSummary(counts);
    } catch (err) {
      if (requestNumber !== latestRequest.current) return;
      setError(err.message);
    } finally {
      if (requestNumber === latestRequest.current) setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    load();
  }, [load]);

  const canManage = can(PERM_MANAGE);
  const canRecordStock = can(PERM_STOCK);

  // The stock dialog expects a product-shaped object
  const asProduct = (row) => ({
    id: row.item_id,
    name: row.item_name,
    sku: row.sku,
    unit: row.unit,
    quantity: row.quantity,
    reorder_threshold: row.reorder_threshold,
  });

  function handleStockSaved(result) {
    setStockTarget(null);
    const { movement, item, already_applied: alreadyApplied } = result;
    if (alreadyApplied) {
      toast.success(`That change was already recorded. ${item.name} stays at ${item.quantity} ${item.unit}.`);
    } else {
      const verb = movement.quantity_change > 0 ? "Added" : "Removed";
      const tail = item.stock_status === "in_stock" ? " The alert is resolved." : "";
      toast.success(`${verb} ${Math.abs(movement.quantity_change)} ${item.unit}. ${item.name} is now ${item.quantity} ${item.unit}.${tail}`);
    }
    load();
  }

  function handleThresholdSaved(newThreshold, newStatus) {
    const name = thresholdTarget.item_name;
    setThresholdTarget(null);
    toast.success(
      newStatus === "in_stock"
        ? `Reorder level for ${name} is now ${newThreshold}. Its alert is resolved.`
        : `Reorder level for ${name} is now ${newThreshold}.`
    );
    load();
  }

  const showEmpty = !loading && !error && rows.length === 0;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Stock Alerts</h1>
          <p className="text-sm text-slate-500">
            Products at or below their reorder level in {business.name}. Alerts open and close automatically.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <SummaryCard label="Open alerts" value={summary?.open} tone="neutral" />
        <SummaryCard label="Critical" value={summary?.critical} tone="red" hint={URGENCY_HELP.critical} />
        <SummaryCard label="Urgent" value={summary?.urgent} tone="orange" hint={URGENCY_HELP.urgent} />
        <SummaryCard label="Low" value={summary?.low} tone="amber" hint={URGENCY_HELP.low} />
        <SummaryCard label="Resolved" value={summary?.resolved} tone="green" />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4">
          <div className="inline-flex rounded-lg bg-slate-100 p-1 text-sm font-medium" role="tablist" aria-label="Alert view">
            {[
              ["open", "Open alerts"],
              ["resolved", "Resolved"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={view === value}
                onClick={() => setView(value)}
                className={`rounded-md px-4 py-1.5 ${view === value ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
              >
                {label}
              </button>
            ))}
          </div>
          {view === "open" && <p className="text-xs text-slate-500">Most urgent first. The emptiest products are at the top.</p>}
        </div>

        {error && (
          <div role="alert" className="m-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>Could not load alerts: {error}</span>
            <button type="button" onClick={load} className="rounded-md bg-white px-3 py-1 font-medium text-red-700 ring-1 ring-red-200 hover:bg-red-100">
              Try again
            </button>
          </div>
        )}

        {loading && rows.length === 0 && !error && <Spinner label="Loading alerts…" />}

        {showEmpty && view === "open" && (
          <div className="px-4 py-16 text-center">
            <p className="text-base font-medium text-slate-900">No low-stock alerts</p>
            <p className="mt-1 text-sm text-slate-500">Every product is above its reorder level.</p>
            <Link to="/inventory" className="mt-3 inline-block text-sm font-medium text-indigo-600 hover:text-indigo-800">
              Go to Inventory
            </Link>
          </div>
        )}

        {showEmpty && view === "resolved" && (
          <div className="px-4 py-16 text-center">
            <p className="text-base font-medium text-slate-900">No resolved alerts yet</p>
            <p className="mt-1 text-sm text-slate-500">Alerts appear here after the stock has been replenished.</p>
          </div>
        )}

        {rows.length > 0 && (
          <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}>
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  {view === "open" && <th className="px-4 py-3 font-medium">Urgency</th>}
                  <th className="px-4 py-3 font-medium">Product</th>
                  <th className="hidden px-4 py-3 font-medium lg:table-cell">Supplier</th>
                  <th className="px-4 py-3 text-right font-medium">In stock</th>
                  <th className="px-4 py-3 text-right font-medium">Reorder at</th>
                  {view === "open" ? (
                    <>
                      <th className="hidden px-4 py-3 text-right font-medium md:table-cell">Below by</th>
                      <th className="hidden px-4 py-3 font-medium md:table-cell">Alert since</th>
                      <th className="px-4 py-3 text-right font-medium">Actions</th>
                    </>
                  ) : (
                    <>
                      <th className="px-4 py-3 font-medium">Status now</th>
                      <th className="hidden px-4 py-3 font-medium md:table-cell">Opened</th>
                      <th className="px-4 py-3 font-medium">Resolved</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-50/60">
                    {view === "open" && (
                      <td className="px-4 py-3">
                        <UrgencyBadge urgency={row.urgency} />
                      </td>
                    )}
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{row.item_name}</p>
                      <p className="text-xs text-slate-500">
                        {row.sku} · {row.category}
                      </p>
                    </td>
                    <td className="hidden px-4 py-3 lg:table-cell">{row.supplier_name ?? "—"}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-semibold tabular-nums">
                      {row.quantity} <span className="font-normal text-slate-500">{row.unit}</span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{row.reorder_threshold}</td>

                    {view === "open" ? (
                      <>
                        <td className="hidden px-4 py-3 text-right tabular-nums md:table-cell">{row.shortfall > 0 ? row.shortfall : "At level"}</td>
                        <td className="hidden whitespace-nowrap px-4 py-3 text-slate-600 md:table-cell">{formatDateTime(row.opened_at)}</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap justify-end gap-1">
                            {canRecordStock && (
                              <RowButton primary onClick={() => setStockTarget(row)}>
                                Add stock
                              </RowButton>
                            )}
                            {canManage && <RowButton onClick={() => setThresholdTarget(row)}>Reorder level</RowButton>}
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-4 py-3">
                          <StatusBadge status={row.stock_status} />
                        </td>
                        <td className="hidden whitespace-nowrap px-4 py-3 text-slate-600 md:table-cell">{formatDateTime(row.opened_at)}</td>
                        <td className="px-4 py-3 text-slate-600">
                          <p className="whitespace-nowrap">{formatDateTime(row.resolved_at)}</p>
                          <p className="text-xs text-slate-500">{RESOLUTION_LABELS[row.resolution] ?? row.resolution}</p>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!canManage && (
        <p className="text-xs text-slate-500">Only the Owner can change reorder levels. You can still add stock to resolve an alert.</p>
      )}

      {stockTarget && <StockMovementModal item={asProduct(stockTarget)} onClose={() => setStockTarget(null)} onSaved={handleStockSaved} />}
      {thresholdTarget && <ThresholdModal item={thresholdTarget} onClose={() => setThresholdTarget(null)} onSaved={handleThresholdSaved} />}
    </div>
  );
}
