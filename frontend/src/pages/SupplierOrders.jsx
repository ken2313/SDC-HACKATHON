import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { supplierOrdersApi } from "../api/supplierOrders.js";
import CancelOrderModal from "../components/CancelOrderModal.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import OrderStatusBadge from "../components/OrderStatusBadge.jsx";
import ReceiveDeliveryModal from "../components/ReceiveDeliveryModal.jsx";
import Spinner from "../components/Spinner.jsx";
import StatusUpdateModal from "../components/StatusUpdateModal.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { formatDateOnly, formatRM } from "../utils/money.js";
import { formatDateTime } from "../utils/stock.js";

const PERM_TRACK = "orders:track";
const PERM_PLACE = "orders:place";

const TABS = [
  ["active", "In progress"],
  ["overdue", "Overdue"],
  ["delivered", "Delivered"],
  ["cancelled", "Cancelled"],
  ["all", "All"],
];

const EMPTY_TEXT = {
  active: ["No orders in progress", "Orders appear here after the owner approves them in Purchase Orders."],
  overdue: ["No overdue deliveries", "An order is overdue when its expected date has passed and it has not been delivered."],
  delivered: ["No delivered orders yet", "Confirm a delivery to add the goods to your stock."],
  cancelled: ["No cancelled orders", "Orders the owner cancels are kept here with the reason."],
  all: ["No supplier orders yet", "Approve a purchase order to start tracking it."],
};

function SummaryCard({ label, value, tone = "neutral", hint }) {
  const tones = { neutral: "text-slate-900", red: "text-red-600", orange: "text-orange-600", indigo: "text-indigo-600", green: "text-emerald-600" };
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
    success: "bg-emerald-600 text-white hover:bg-emerald-700",
    danger: "border border-red-200 text-red-700 hover:bg-red-50",
    plain: "border border-slate-300 text-slate-700 hover:bg-slate-50",
  };
  return (
    <button type="button" onClick={onClick} className={`rounded-lg px-3 py-1.5 text-sm font-medium ${styles[variant]}`}>
      {children}
    </button>
  );
}

function Timeline({ history }) {
  return (
    <ol className="space-y-2 border-l border-slate-200 pl-4">
      {history.map((entry) => (
        <li key={entry.id} className="relative text-sm">
          <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-indigo-400" />
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <OrderStatusBadge status={entry.to_status} />
            <span className="text-slate-600">
              {entry.user_name} · {formatDateTime(entry.created_at)}
            </span>
          </div>
          {entry.note && <p className="mt-0.5 text-slate-500">{entry.note}</p>}
        </li>
      ))}
    </ol>
  );
}

function OrderCard({ order, canTrack, canPlace, onAction }) {
  const [showTimeline, setShowTimeline] = useState(false);
  const next = order.next_statuses;
  const delivered = order.status === "delivered";
  const isFinal = delivered || order.status === "cancelled";

  return (
    <article className={`rounded-xl border bg-white shadow-sm ${order.is_overdue ? "border-red-300" : "border-slate-200"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-slate-900">{order.po_number}</h2>
            <OrderStatusBadge status={order.status} />
            {order.is_overdue && (
              <span className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 ring-1 ring-inset ring-red-600/20">
                Overdue by {order.days_overdue} day{order.days_overdue === 1 ? "" : "s"}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-slate-600">
            {order.supplier_name}
            {order.supplier_contact ? ` · ${order.supplier_contact}` : ""}
            {order.supplier_phone ? ` · ${order.supplier_phone}` : ""}
          </p>
        </div>
        <div className="text-right text-sm">
          <p className="font-semibold text-slate-900">{formatRM(order.total)}</p>
          {!isFinal && (
            <p className={order.is_overdue ? "font-medium text-red-600" : "text-slate-500"}>
              Expected {formatDateOnly(order.estimated_delivery_date)}
              {order.status === "approved" ? " (estimate, not placed yet)" : ""}
            </p>
          )}
          {delivered && <p className="text-slate-500">Delivered {formatDateTime(order.updated_at)}</p>}
        </div>
      </div>

      <div className="overflow-x-auto border-t border-slate-100">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Product</th>
              <th className="px-4 py-2 text-right font-medium">Ordered</th>
              {delivered && <th className="px-4 py-2 text-right font-medium">Received</th>}
              <th className="px-4 py-2 text-right font-medium">Line total</th>
            </tr>
          </thead>
          <tbody>
            {order.lines.map((line) => (
              <tr key={line.id} className="border-t border-slate-100">
                <td className="px-4 py-2">
                  <span className="font-medium text-slate-900">{line.item_name}</span>
                  <span className="ml-2 text-xs text-slate-500">{line.sku}</span>
                </td>
                <td className="px-4 py-2 text-right text-slate-700">
                  {line.quantity_ordered} {line.unit}
                </td>
                {delivered && (
                  <td className={`px-4 py-2 text-right ${line.received_quantity < line.quantity_ordered ? "font-medium text-amber-700" : "text-slate-700"}`}>
                    {line.received_quantity} {line.unit}
                  </td>
                )}
                <td className="px-4 py-2 text-right text-slate-700">{formatRM(line.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3">
        <button type="button" onClick={() => setShowTimeline((open) => !open)} className="text-sm font-medium text-indigo-600 hover:text-indigo-800">
          {showTimeline ? "Hide timeline" : `Timeline (${order.history.length})`}
        </button>
        <div className="flex flex-wrap items-center gap-2">
          {next.includes("ordered") && canPlace && (
            <ActionButton variant="primary" onClick={() => onAction("place", order)}>Place with supplier (simulated)</ActionButton>
          )}
          {next.includes("shipped") && canTrack && <ActionButton onClick={() => onAction("shipped", order)}>Mark shipped</ActionButton>}
          {next.includes("delayed") && canTrack && <ActionButton onClick={() => onAction("delayed", order)}>Mark delayed</ActionButton>}
          {next.includes("delivered") && canTrack && <ActionButton variant="success" onClick={() => onAction("receive", order)}>Confirm delivery</ActionButton>}
          {next.includes("cancelled") && canPlace && <ActionButton variant="danger" onClick={() => onAction("cancel", order)}>Cancel order</ActionButton>}
          {!isFinal && !canPlace && order.status === "approved" && (
            <span className="text-xs text-slate-500">Waiting for the owner to place this order.</span>
          )}
        </div>
      </div>

      {showTimeline && (
        <div className="border-t border-slate-100 px-4 py-4">
          <Timeline history={order.history} />
        </div>
      )}
    </article>
  );
}

export default function SupplierOrders() {
  const { can, business } = useSession();
  const toast = useToast();
  const canTrack = can(PERM_TRACK);
  const canPlace = can(PERM_PLACE);

  const [view, setView] = useState("active");
  const [orders, setOrders] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [placeTarget, setPlaceTarget] = useState(null);
  const [statusTarget, setStatusTarget] = useState(null); // { order, status }
  const [receiveTarget, setReceiveTarget] = useState(null);
  const [cancelTarget, setCancelTarget] = useState(null);

  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    const requestNumber = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const [list, counts] = await Promise.all([supplierOrdersApi.list(view), supplierOrdersApi.summary()]);
      if (requestNumber !== latestRequest.current) return;
      setOrders(list);
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

  function handleAction(action, order) {
    if (action === "place") setPlaceTarget(order);
    else if (action === "shipped" || action === "delayed") setStatusTarget({ order, status: action });
    else if (action === "receive") setReceiveTarget(order);
    else if (action === "cancel") setCancelTarget(order);
  }

  async function confirmPlace() {
    const order = placeTarget;
    try {
      await supplierOrdersApi.place(order.id);
      toast.success(`${order.po_number} was marked as placed with ${order.supplier_name} (simulated: nothing was sent).`);
    } catch (err) {
      toast.error(err.message);
    }
    setPlaceTarget(null);
    load();
  }

  function handleStatusSaved(updated) {
    setStatusTarget(null);
    toast.success(`${updated.po_number} is now ${updated.status}.`);
    load();
  }

  function handleReceived(result) {
    setReceiveTarget(null);
    const added = result.stock_updates.map((u) => `${u.item_name} +${u.added} (now ${u.new_quantity} ${u.unit})`).join(", ");
    let message = `${result.order.po_number} delivered. Stock updated: ${added}.`;
    if (result.follow_up_drafts.length) {
      message += ` A new draft (${result.follow_up_drafts.join(", ")}) was prepared because stock is still low.`;
    }
    toast.success(message);
    load();
  }

  function handleCancelled() {
    toast.success(`${cancelTarget.po_number} was cancelled.`);
    setCancelTarget(null);
    load();
  }

  const showEmpty = !loading && !error && orders.length === 0;
  const [emptyTitle, emptyText] = EMPTY_TEXT[view];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Supplier Orders</h1>
          <p className="text-sm text-slate-500">
            Track approved orders from the supplier to your shelf in {business.name}. Supplier actions are simulated.
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

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <SummaryCard label="To place" value={summary?.awaiting_placement} tone="indigo" hint="Approved, not yet sent to the supplier" />
        <SummaryCard label="In transit" value={summary?.in_transit} hint="Ordered or shipped" />
        <SummaryCard label="Delayed" value={summary?.delayed} tone="orange" />
        <SummaryCard label="Overdue" value={summary?.overdue} tone="red" hint="Expected date has passed" />
        <SummaryCard label="Due in 7 days" value={summary?.due_next_7_days} />
        <SummaryCard label="Delivered" value={summary?.delivered} tone="green" />
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setView(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              view === key ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {label}
            {key === "overdue" && summary?.overdue > 0 && (
              <span className="ml-1.5 rounded-full bg-red-100 px-1.5 text-xs text-red-700">{summary.overdue}</span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error}</span>
          <button type="button" onClick={load} className="font-medium underline">Try again</button>
        </div>
      )}

      {loading && orders.length === 0 ? (
        <Spinner label="Loading supplier orders…" />
      ) : showEmpty ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <p className="font-medium text-slate-900">{emptyTitle}</p>
          <p className="mt-1 text-sm text-slate-500">{emptyText}</p>
          <Link to="/purchase-orders" className="mt-4 inline-block text-sm font-medium text-indigo-600 hover:text-indigo-800">
            Go to Purchase Orders
          </Link>
        </div>
      ) : (
        <div className={`space-y-4 ${loading ? "opacity-60" : ""}`}>
          {orders.map((order) => (
            <OrderCard key={order.id} order={order} canTrack={canTrack} canPlace={canPlace} onAction={handleAction} />
          ))}
        </div>
      )}

      {placeTarget && (
        <ConfirmDialog
          title={`Place ${placeTarget.po_number} with ${placeTarget.supplier_name}?`}
          message={`This marks the order (${formatRM(placeTarget.total)}) as placed and sets the expected delivery date from the supplier's usual ${placeTarget.lead_time_days}-day delivery time. This is a simulation: no real message is sent to any supplier.`}
          confirmLabel="Place order"
          onConfirm={confirmPlace}
          onCancel={() => setPlaceTarget(null)}
        />
      )}
      {statusTarget && (
        <StatusUpdateModal order={statusTarget.order} status={statusTarget.status} onClose={() => setStatusTarget(null)} onSaved={handleStatusSaved} />
      )}
      {receiveTarget && <ReceiveDeliveryModal order={receiveTarget} onClose={() => setReceiveTarget(null)} onReceived={handleReceived} />}
      {cancelTarget && <CancelOrderModal order={cancelTarget} onClose={() => setCancelTarget(null)} onCancelled={handleCancelled} />}
    </div>
  );
}
