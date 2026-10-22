import { useCallback, useEffect, useRef, useState } from "react";
import { purchaseOrdersApi } from "../api/purchaseOrders.js";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import OrderEditModal from "../components/OrderEditModal.jsx";
import OrderStatusBadge from "../components/OrderStatusBadge.jsx";
import RejectOrderModal from "../components/RejectOrderModal.jsx";
import Spinner from "../components/Spinner.jsx";
import UrgencyBadge from "../components/UrgencyBadge.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { formatDateOnly, formatRM } from "../utils/money.js";
import { formatDateTime } from "../utils/stock.js";

const PERM_PREPARE = "orders:prepare";
const PERM_APPROVE = "orders:approve";

const TABS = [
  ["awaiting", "Awaiting approval"],
  ["approved", "Approved"],
  ["rejected", "Rejected"],
  ["all", "All orders"],
];

const EMPTY_TEXT = {
  awaiting: ["Nothing is waiting for approval", "When a product runs low, a draft order appears here for the owner to review."],
  approved: ["No approved orders yet", "Orders appear here after the owner approves them."],
  rejected: ["No rejected orders", "Orders the owner rejects are kept here with the reason."],
  all: ["No purchase orders yet", "Orders are prepared automatically when stock runs low, or press “Check restocking needs”."],
};

function SummaryCard({ label, value, tone, hint }) {
  const tones = { neutral: "text-slate-900", amber: "text-amber-600", green: "text-emerald-600", indigo: "text-indigo-600" };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" title={hint}>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tones[tone]}`}>{value ?? "–"}</p>
    </div>
  );
}

function ActionButton({ onClick, children, variant = "plain" }) {
  const styles = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700",
    danger: "border border-red-200 text-red-700 hover:bg-red-50",
    plain: "border border-slate-300 text-slate-700 hover:bg-slate-50",
  };
  return (
    <button type="button" onClick={onClick} className={`rounded-lg px-3 py-1.5 text-sm font-medium ${styles[variant]}`}>
      {children}
    </button>
  );
}

function NeedsPanel({ needs, canPrepare, generating, onGenerate }) {
  const ready = needs.filter((need) => !need.blocked_reason);
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/50 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Low products without an order</h2>
          <p className="text-xs text-slate-600">
            Suggested quantity = refill to 2 × the reorder level (at least the supplier&apos;s minimum). Supplier = cheapest price.
          </p>
        </div>
        {canPrepare && ready.length > 0 && (
          <button
            type="button"
            onClick={onGenerate}
            disabled={generating}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {generating ? "Preparing…" : `Prepare ${ready.length} draft${ready.length === 1 ? "" : "s"}`}
          </button>
        )}
      </div>
      <ul className="divide-y divide-amber-100">
        {needs.map((need) => (
          <li key={need.item_id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm">
            <div className="flex items-center gap-3">
              <UrgencyBadge urgency={need.urgency} />
              <div>
                <p className="font-medium text-slate-900">{need.item_name}</p>
                <p className="text-xs text-slate-500">
                  {need.quantity} {need.unit} left · reorder at {need.reorder_threshold}
                </p>
              </div>
            </div>
            {need.blocked_reason ? (
              <p className="text-xs font-medium text-amber-800">{need.blocked_reason}</p>
            ) : (
              <p className="text-right text-xs text-slate-600">
                Order <span className="font-semibold text-slate-900">{need.recommended_quantity}</span> from {need.supplier_name} ·{" "}
                {formatRM(need.estimated_total)}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function OrderCard({ order, canPrepare, canApprove, onEdit, onApprove, onReject }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900">{order.po_number}</h3>
            <OrderStatusBadge status={order.status} />
            {order.source === "auto" && (
              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700" title="Prepared automatically after a low-stock alert">
                Auto-prepared
              </span>
            )}
          </div>
          <p className="mt-0.5 text-sm text-slate-600">
            {order.supplier.name}
            {order.supplier.contact_name ? ` · ${order.supplier.contact_name}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wide text-slate-500">Estimated total</p>
          <p className="text-lg font-semibold text-slate-900">{formatRM(order.total)}</p>
        </div>
      </header>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Product</th>
              <th className="px-4 py-2 text-right font-medium">In stock</th>
              <th className="px-4 py-2 text-right font-medium">Order qty</th>
              <th className="hidden px-4 py-2 text-right font-medium sm:table-cell">Unit price</th>
              <th className="px-4 py-2 text-right font-medium">Line total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {order.lines.map((line) => (
              <tr key={line.id}>
                <td className="px-4 py-2">
                  <p className="font-medium text-slate-900">{line.item_name}</p>
                  <p className="text-xs text-slate-500">{line.sku}</p>
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums">
                  {line.current_quantity} <span className="text-slate-500">{line.unit}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right font-semibold tabular-nums">
                  {line.quantity_ordered} <span className="font-normal text-slate-500">{line.unit}</span>
                  {line.quantity_ordered !== line.recommended_quantity && (
                    <span className="ml-1 text-xs font-normal text-amber-700" title={`The system suggested ${line.recommended_quantity}`}>
                      (edited)
                    </span>
                  )}
                </td>
                <td className="hidden px-4 py-2 text-right tabular-nums sm:table-cell">{formatRM(line.unit_price)}</td>
                <td className="px-4 py-2 text-right tabular-nums">{formatRM(line.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <footer className="space-y-3 border-t border-slate-100 px-4 py-3">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
          <span>Est. delivery: {formatDateOnly(order.estimated_delivery_date)} ({order.supplier.lead_time_days} day{order.supplier.lead_time_days === 1 ? "" : "s"} typical)</span>
          <span>
            Prepared {formatDateTime(order.created_at)}
            {order.created_by_name ? ` by ${order.created_by_name}` : ""}
          </span>
        </div>

        {order.notes && <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">Note: {order.notes}</p>}

        {order.status === "approved" && (
          <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            Approved by {order.decided_by_name} on {formatDateTime(order.decided_at)}. Placing it with the supplier and tracking delivery come in Feature 5.
          </p>
        )}
        {order.status === "rejected" && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">
            Rejected by {order.decided_by_name} on {formatDateTime(order.decided_at)}. Reason: {order.decision_note}
          </p>
        )}

        {order.is_editable && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            {canApprove ? (
              <p className="text-xs text-slate-500">Nothing is ordered until you approve.</p>
            ) : (
              <p className="text-xs text-slate-500">Waiting for the owner to approve. Employees can prepare and edit orders but cannot approve them.</p>
            )}
            <div className="flex flex-wrap gap-2">
              {canPrepare && <ActionButton onClick={() => onEdit(order)}>Edit</ActionButton>}
              {canApprove && (
                <>
                  <ActionButton variant="danger" onClick={() => onReject(order)}>
                    Reject
                  </ActionButton>
                  <ActionButton variant="primary" onClick={() => onApprove(order)}>
                    Approve
                  </ActionButton>
                </>
              )}
            </div>
          </div>
        )}
      </footer>
    </article>
  );
}

export default function PurchaseOrders() {
  const { can, business } = useSession();
  const toast = useToast();

  const [tab, setTab] = useState("awaiting");
  const [orders, setOrders] = useState([]);
  const [summary, setSummary] = useState(null);
  const [needs, setNeeds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);

  const [editTarget, setEditTarget] = useState(null);
  const [approveTarget, setApproveTarget] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);

  const latestRequest = useRef(0); // only the newest request may update the screen

  const load = useCallback(async () => {
    const requestNumber = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const [list, counts, needList] = await Promise.all([
        purchaseOrdersApi.list(tab),
        purchaseOrdersApi.summary(),
        purchaseOrdersApi.needs(),
      ]);
      if (requestNumber !== latestRequest.current) return;
      setOrders(list);
      setSummary(counts);
      setNeeds(needList);
    } catch (err) {
      if (requestNumber !== latestRequest.current) return;
      setError(err.message);
    } finally {
      if (requestNumber === latestRequest.current) setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    load();
  }, [load]);

  const canPrepare = can(PERM_PREPARE);
  const canApprove = can(PERM_APPROVE);

  async function handleGenerate() {
    if (generating) return;
    setGenerating(true);
    try {
      const result = await purchaseOrdersApi.generate();
      if (result.lines_added === 0) {
        toast.success(
          result.skipped.length > 0
            ? `No drafts could be made: ${result.skipped.length} low product(s) have no supplier price on file.`
            : "Nothing to order. Every low product already has an order."
        );
      } else {
        const skippedNote = result.skipped.length > 0 ? ` ${result.skipped.length} product(s) were skipped (no supplier price).` : "";
        toast.success(
          `Prepared ${result.lines_added} product line(s) in ${result.orders.length} draft order(s). Nothing is ordered until the owner approves.${skippedNote}`
        );
        setTab("awaiting");
      }
      await load();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleApprove() {
    const order = approveTarget;
    try {
      await purchaseOrdersApi.approve(order.id);
      toast.success(`Approved ${order.po_number} (${formatRM(order.total)}).`);
    } catch (err) {
      toast.error(err.message);
    }
    setApproveTarget(null);
    load();
  }

  function handleRejected() {
    toast.success(`Rejected ${rejectTarget.po_number}.`);
    setRejectTarget(null);
    load();
  }

  async function handleEditChanged(message, { close = false } = {}) {
    toast.success(message);
    if (close) setEditTarget(null);
    await load();
  }

  const showEmpty = !loading && !error && orders.length === 0;
  const [emptyTitle, emptyText] = EMPTY_TEXT[tab];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Purchase Orders</h1>
          <p className="text-sm text-slate-500">
            Draft orders for {business.name}, prepared when stock runs low. Only the owner can approve or reject.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          {canPrepare && (
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
            >
              {generating ? "Checking…" : "Check restocking needs"}
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryCard label="Awaiting approval" value={summary?.awaiting_approval} tone="amber" hint="Draft orders waiting for the owner" />
        <SummaryCard label="Value awaiting" value={summary ? formatRM(summary.awaiting_value) : null} tone="neutral" hint="Total of orders waiting for approval" />
        <SummaryCard label="Approved" value={summary?.approved} tone="green" />
        <SummaryCard label="Low, no order yet" value={summary ? summary.needs_ordering + summary.no_supplier : null} tone="indigo" hint="Products with an open low-stock alert and no order" />
      </div>

      {needs.length > 0 && <NeedsPanel needs={needs} canPrepare={canPrepare} generating={generating} onGenerate={handleGenerate} />}

      <div className="space-y-4">
        <div className="inline-flex flex-wrap rounded-lg bg-slate-100 p-1 text-sm font-medium" role="tablist" aria-label="Order view">
          {TABS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => setTab(value)}
              className={`rounded-md px-4 py-1.5 ${tab === value ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
            >
              {label}
            </button>
          ))}
        </div>

        {error && (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>Could not load purchase orders: {error}</span>
            <button type="button" onClick={load} className="rounded-md bg-white px-3 py-1 font-medium text-red-700 ring-1 ring-red-200 hover:bg-red-100">
              Try again
            </button>
          </div>
        )}

        {loading && orders.length === 0 && !error && <Spinner label="Loading purchase orders…" />}

        {showEmpty && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-14 text-center">
            <p className="text-base font-medium text-slate-900">{emptyTitle}</p>
            <p className="mt-1 text-sm text-slate-500">{emptyText}</p>
          </div>
        )}

        <div className={`space-y-4 ${loading && orders.length > 0 ? "opacity-60" : ""}`}>
          {orders.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              canPrepare={canPrepare}
              canApprove={canApprove}
              onEdit={setEditTarget}
              onApprove={setApproveTarget}
              onReject={setRejectTarget}
            />
          ))}
        </div>
      </div>

      {editTarget && <OrderEditModal order={editTarget} onClose={() => setEditTarget(null)} onChanged={handleEditChanged} />}

      {approveTarget && (
        <ConfirmDialog
          title={`Approve ${approveTarget.po_number}?`}
          message={`You are approving an order of ${formatRM(approveTarget.total)} from ${approveTarget.supplier.name} (${approveTarget.lines.length} product${approveTarget.lines.length === 1 ? "" : "s"}). Your decision is saved in the activity log. This step does not contact the supplier: placing the order is a simulated action added in Feature 5.`}
          confirmLabel="Approve order"
          onConfirm={handleApprove}
          onCancel={() => setApproveTarget(null)}
        />
      )}

      {rejectTarget && <RejectOrderModal order={rejectTarget} onClose={() => setRejectTarget(null)} onRejected={handleRejected} />}
    </div>
  );
}
