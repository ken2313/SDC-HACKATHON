import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { suppliersApi } from "../api/suppliers.js";
import { useToast } from "../context/ToastContext.jsx";
import { formatDateOnly, formatRM } from "../utils/money.js";
import { formatDateTime } from "../utils/stock.js";
import ConfirmDialog from "./ConfirmDialog.jsx";
import Modal from "./Modal.jsx";
import OrderStatusBadge from "./OrderStatusBadge.jsx";
import Spinner from "./Spinner.jsx";
import StatusBadge from "./StatusBadge.jsx";
import SupplierFormModal from "./SupplierFormModal.jsx";
import SupplierPriceModal from "./SupplierPriceModal.jsx";

function Stat({ label, value, hint, tone = "text-slate-900" }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2" title={hint}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-0.5 text-base font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

function ContactRow({ label, children }) {
  return (
    <div className="grid grid-cols-3 gap-3 py-2 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="col-span-2 break-words text-slate-900">{children || <span className="text-slate-400">Not recorded</span>}</dd>
    </div>
  );
}

function PriceList({ supplier, canManage, onEdit, onRemove }) {
  if (supplier.products.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500">
        No products on this price list yet. Purchase order drafts can only use a supplier that has a price for the product.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2 font-medium">Product</th>
            <th className="px-3 py-2 text-right font-medium">Price</th>
            <th className="px-3 py-2 text-right font-medium">Min order</th>
            <th className="px-3 py-2 font-medium">Stock</th>
            <th className="px-3 py-2 font-medium">Auto orders</th>
            {canManage && <th className="px-3 py-2"><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {supplier.products.map((line) => (
            <tr key={line.id} className="border-t border-slate-100 align-top">
              <td className="px-3 py-2">
                <p className="font-medium text-slate-900">{line.item_name}</p>
                <p className="text-xs text-slate-500">
                  {line.sku} · {line.category}
                  {line.item_archived && <span className="ml-1 font-medium text-slate-600">(archived)</span>}
                </p>
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right text-slate-900">
                {formatRM(line.unit_price)}
                <span className="block text-xs text-slate-500">per {line.unit}</span>
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right text-slate-700">{line.min_order_qty}</td>
              <td className="px-3 py-2">
                <StatusBadge status={line.stock_status} />
                <span className="mt-1 block text-xs text-slate-500">
                  {line.current_quantity} {line.unit} · reorder at {line.reorder_threshold}
                </span>
              </td>
              <td className="px-3 py-2 text-xs">
                {line.chosen_for_auto_orders ? (
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                    Chosen
                  </span>
                ) : (
                  <span className="text-slate-500">Another supplier is cheaper or faster</span>
                )}
                {line.other_suppliers > 0 && (
                  <span className="mt-1 block text-slate-500">
                    {line.other_suppliers} other supplier{line.other_suppliers === 1 ? "" : "s"}
                  </span>
                )}
              </td>
              {canManage && (
                <td className="whitespace-nowrap px-3 py-2 text-right">
                  <button type="button" onClick={() => onEdit(line)} className="text-sm font-medium text-indigo-600 hover:text-indigo-800">
                    Price
                  </button>
                  <button type="button" onClick={() => onRemove(line)} className="ml-3 text-sm font-medium text-red-600 hover:text-red-800">
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OrderHistory({ supplier }) {
  if (supplier.orders.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500">
        No orders with this supplier yet.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2 font-medium">Order</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 text-right font-medium">Value</th>
            <th className="px-3 py-2 font-medium">Placed</th>
            <th className="px-3 py-2 font-medium">Delivery</th>
          </tr>
        </thead>
        <tbody>
          {supplier.orders.map((order) => (
            <tr key={order.id} className="border-t border-slate-100 align-top">
              <td className="px-3 py-2">
                <p className="font-medium text-slate-900">{order.po_number}</p>
                <p className="text-xs text-slate-500">
                  {order.line_count} product{order.line_count === 1 ? "" : "s"} · created {formatDateTime(order.created_at)}
                </p>
              </td>
              <td className="px-3 py-2"><OrderStatusBadge status={order.status} /></td>
              <td className="whitespace-nowrap px-3 py-2 text-right text-slate-900">
                {formatRM(order.total)}
                {order.status === "delivered" && order.received_value !== order.total && (
                  <span className="block text-xs text-amber-700">received {formatRM(order.received_value)}</span>
                )}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-slate-600">{order.placed_at ? formatDateTime(order.placed_at) : "–"}</td>
              <td className="px-3 py-2 text-slate-600">
                {order.status === "delivered" ? (
                  <>
                    {order.delivered_at ? formatDateTime(order.delivered_at) : "Delivered"}
                    {order.delivery_days !== null && (
                      <span className={`block text-xs ${order.late ? "font-medium text-red-600" : "text-slate-500"}`}>
                        {order.delivery_days} day{order.delivery_days === 1 ? "" : "s"}
                        {order.late ? ` (usually ${supplier.lead_time_days})` : ""}
                      </span>
                    )}
                  </>
                ) : order.estimated_delivery_date && !["rejected", "cancelled"].includes(order.status) ? (
                  <span>Expected {formatDateOnly(order.estimated_delivery_date)}</span>
                ) : (
                  "–"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Everything about one supplier: contact details, price list, order history.
// Owners can edit, deactivate and change prices. The backend checks the role again.
export default function SupplierDetailModal({ supplierId, canManage, onClose, onChanged }) {
  const toast = useToast();
  const [supplier, setSupplier] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("prices");

  const [editing, setEditing] = useState(false);
  const [priceTarget, setPriceTarget] = useState(null); // { line } ; line = null means "add"
  const [removeTarget, setRemoveTarget] = useState(null);
  const [toggleActive, setToggleActive] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSupplier(await suppliersApi.get(supplierId));
    } catch (err) {
      setError(err.message);
    }
  }, [supplierId]);

  useEffect(() => {
    load();
  }, [load]);

  function changed(updated) {
    setSupplier(updated);
    onChanged();
  }

  function handleSaved(updated) {
    setEditing(false);
    changed(updated);
    toast.success(`${updated.name} was saved.`);
  }

  function handlePriceSaved(result, isEdit) {
    setPriceTarget(null);
    changed(result.supplier);
    if (isEdit) {
      toast.success("Price saved. New purchase order drafts use it; orders already prepared keep their price.");
    } else if (result.draft_purchase_order) {
      toast.success(`Added to the price list. The product is low, so draft ${result.draft_purchase_order.po_number} was prepared for the owner to approve.`);
    } else {
      toast.success("Added to the price list.");
    }
  }

  async function confirmRemove() {
    const line = removeTarget;
    try {
      changed(await suppliersApi.removeProduct(supplier.id, line.id));
      toast.success(`${line.item_name} was removed from ${supplier.name}'s price list.`);
    } catch (err) {
      toast.error(err.message);
    }
    setRemoveTarget(null);
  }

  async function confirmToggleActive() {
    try {
      const updated = supplier.is_active ? await suppliersApi.deactivate(supplier.id) : await suppliersApi.activate(supplier.id);
      changed(updated);
      toast.success(updated.is_active ? `${updated.name} is active again.` : `${updated.name} was deactivated.`);
    } catch (err) {
      toast.error(err.message);
    }
    setToggleActive(false);
  }

  const stats = supplier?.stats;
  // While a dialog is open on top of this one, `busy` stops Esc from closing both at once
  const childOpen = editing || Boolean(priceTarget) || Boolean(removeTarget) || toggleActive;
  const tabs = supplier
    ? [
        ["prices", `Price list (${supplier.products.length})`],
        ["orders", `Order history (${supplier.orders.length})`],
        ["contact", "Contact"],
      ]
    : [];

  return (
    <>
      <Modal
        title={supplier?.name ?? "Supplier"}
        subtitle={
          supplier
            ? `${supplier.is_active ? "Active" : "Inactive: not used for new orders"} · usually delivers in ${supplier.lead_time_days} day${supplier.lead_time_days === 1 ? "" : "s"}`
            : undefined
        }
        onClose={onClose}
        size="lg"
        busy={childOpen}
      >
        {error ? (
          <div role="alert" className="flex items-center justify-between gap-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>{error}</span>
            <button type="button" onClick={load} className="font-medium underline">Try again</button>
          </div>
        ) : !supplier ? (
          <Spinner label="Loading supplier…" />
        ) : (
          <div className="space-y-5">
            {canManage && (
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setEditing(true)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
                  Edit details
                </button>
                <button type="button" onClick={() => setPriceTarget({ line: null })} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700">
                  Add product
                </button>
                <button
                  type="button"
                  onClick={() => setToggleActive(true)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                    supplier.is_active ? "border border-red-200 text-red-700 hover:bg-red-50" : "border border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                  }`}
                >
                  {supplier.is_active ? "Deactivate" : "Re-activate"}
                </button>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <Stat label="Open orders" value={supplier.open_orders} hint="Draft, approved, ordered, shipped or delayed" />
              <Stat label="Delivered" value={stats.delivered} />
              <Stat label="Received value" value={formatRM(stats.delivered_value)} hint="Received quantities x order prices" />
              <Stat
                label="Avg delivery"
                value={stats.average_delivery_days === null ? "–" : `${stats.average_delivery_days} d`}
                hint={`From placing to delivery, over ${stats.measured_deliveries} delivered order(s). Usual: ${supplier.lead_time_days} day(s).`}
              />
              <Stat label="Late deliveries" value={stats.late_deliveries} tone={stats.late_deliveries > 0 ? "text-red-600" : "text-slate-900"} hint="Took longer than the usual delivery time" />
            </div>

            <div className="flex flex-wrap gap-1 border-b border-slate-200">
              {tabs.map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTab(key)}
                  className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
                    tab === key ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {tab === "prices" && (
              <PriceList
                supplier={supplier}
                canManage={canManage}
                onEdit={(line) => setPriceTarget({ line })}
                onRemove={(line) => setRemoveTarget(line)}
              />
            )}
            {tab === "orders" && (
              <>
                <OrderHistory supplier={supplier} />
                <p className="text-xs text-slate-500">
                  Work on these orders in <Link to="/purchase-orders" onClick={onClose} className="font-medium text-indigo-600 hover:text-indigo-800">Purchase Orders</Link> and{" "}
                  <Link to="/supplier-orders" onClick={onClose} className="font-medium text-indigo-600 hover:text-indigo-800">Supplier Orders</Link>.
                </p>
              </>
            )}
            {tab === "contact" && (
              <dl className="divide-y divide-slate-100">
                <ContactRow label="Contact person">{supplier.contact_name}</ContactRow>
                <ContactRow label="Phone">
                  {supplier.phone && <a href={`tel:${supplier.phone.replace(/[^\d+]/g, "")}`} className="text-indigo-600 hover:text-indigo-800">{supplier.phone}</a>}
                </ContactRow>
                <ContactRow label="Email">
                  {supplier.email && <a href={`mailto:${supplier.email}`} className="text-indigo-600 hover:text-indigo-800">{supplier.email}</a>}
                </ContactRow>
                <ContactRow label="Address">{supplier.address}</ContactRow>
                <ContactRow label="Notes">{supplier.notes}</ContactRow>
                <ContactRow label="Usual delivery">{`${supplier.lead_time_days} day${supplier.lead_time_days === 1 ? "" : "s"}`}</ContactRow>
                <ContactRow label="Last updated">{formatDateTime(supplier.updated_at)}</ContactRow>
              </dl>
            )}
          </div>
        )}
      </Modal>

      {editing && <SupplierFormModal supplier={supplier} onClose={() => setEditing(false)} onSaved={handleSaved} />}
      {priceTarget && (
        <SupplierPriceModal supplier={supplier} line={priceTarget.line} onClose={() => setPriceTarget(null)} onSaved={handlePriceSaved} />
      )}
      {removeTarget && (
        <ConfirmDialog
          title={`Remove ${removeTarget.item_name}?`}
          message={`${supplier.name} will no longer be used for new ${removeTarget.item_name} orders. Orders already prepared are not changed. ${
            removeTarget.other_suppliers === 0 ? "No other active supplier sells this product, so it cannot be reordered until you add a price again." : ""
          }`}
          confirmLabel="Remove"
          danger
          onConfirm={confirmRemove}
          onCancel={() => setRemoveTarget(null)}
        />
      )}
      {toggleActive && (
        <ConfirmDialog
          title={supplier.is_active ? `Deactivate ${supplier.name}?` : `Re-activate ${supplier.name}?`}
          message={
            supplier.is_active
              ? "The supplier and its order history are kept, but it will not be chosen for new purchase orders. A supplier with unfinished orders cannot be deactivated."
              : "The supplier can be chosen for new purchase orders again, using its current price list."
          }
          confirmLabel={supplier.is_active ? "Deactivate" : "Re-activate"}
          danger={supplier.is_active}
          onConfirm={confirmToggleActive}
          onCancel={() => setToggleActive(false)}
        />
      )}
    </>
  );
}
