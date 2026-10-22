import { useState } from "react";
import { purchaseOrdersApi } from "../api/purchaseOrders.js";
import { formatRM } from "../utils/money.js";
import { isWholeNumber } from "../utils/stock.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";

// Change the supplier, the quantities or the note of an order that is still waiting for a decision.
// Prices cannot be typed in: they come from the supplier's price list.
// `onChanged` runs after every successful server change (so the list behind the dialog stays current).
export default function OrderEditModal({ order: initialOrder, onClose, onChanged }) {
  const [order, setOrder] = useState(initialOrder);
  const [supplierId, setSupplierId] = useState(initialOrder.supplier.id);
  const [notes, setNotes] = useState(initialOrder.notes ?? "");
  const [quantities, setQuantities] = useState(
    Object.fromEntries(initialOrder.lines.map((line) => [line.id, String(line.quantity_ordered)]))
  );
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);

  const supplierChanged = supplierId !== order.supplier.id;

  // Validate the typed quantities
  const lineErrors = {};
  order.lines.forEach((line) => {
    const text = quantities[line.id] ?? "";
    if (!isWholeNumber(text) || Number(text) < 1) {
      lineErrors[line.id] = "Whole number, 1 or more.";
    } else if (
      Number(text) !== line.quantity_ordered &&
      line.min_order_qty &&
      Number(text) < line.min_order_qty
    ) {
      lineErrors[line.id] = `Supplier minimum is ${line.min_order_qty}.`;
    }
  });
  const hasLineErrors = Object.keys(lineErrors).length > 0;

  const changedLines = order.lines.filter(
    (line) => !lineErrors[line.id] && Number(quantities[line.id]) !== line.quantity_ordered
  );
  const notesChanged = notes.trim() !== (order.notes ?? "");
  const hasChanges = supplierChanged || notesChanged || changedLines.length > 0;

  const previewTotal = order.lines.reduce(
    (sum, line) => sum + (lineErrors[line.id] ? 0 : Number(quantities[line.id]) * line.unit_price),
    0
  );

  async function handleRemove(line) {
    if (saving) return;
    setSaving(true);
    setServerError(null);
    try {
      const updated = await purchaseOrdersApi.removeLine(order.id, line.id);
      setOrder(updated);
      setQuantities((current) => {
        const next = { ...current };
        delete next[line.id];
        return next;
      });
      onChanged(`Removed ${line.item_name} from ${updated.po_number}.`);
    } catch (error) {
      setServerError(error.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || !hasChanges || hasLineErrors) return;
    const payload = {};
    if (supplierChanged) payload.supplier_id = supplierId;
    if (notesChanged) payload.notes = notes.trim();
    if (changedLines.length > 0 || supplierChanged) {
      // When the supplier changes the server re-prices every line; sending the quantities keeps them explicit.
      payload.lines = order.lines.map((line) => ({ line_id: line.id, quantity: Number(quantities[line.id]) }));
    }
    setSaving(true);
    setServerError(null);
    try {
      const updated = await purchaseOrdersApi.update(order.id, payload);
      onChanged(`Saved changes to ${updated.po_number}.`, { close: true });
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  const otherSuppliers = order.eligible_suppliers;

  return (
    <Modal
      title={`Edit ${order.po_number}`}
      subtitle="Changes are saved in the activity log. The order still needs the owner's approval."
      onClose={onClose}
      busy={saving}
      size="lg"
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}

        <FormField
          label="Supplier"
          htmlFor="po-supplier"
          hint={
            supplierChanged
              ? "Prices will switch to this supplier's price list when you save."
              : otherSuppliers.length > 1
              ? "Only suppliers that sell every product on this order are listed."
              : "No other supplier sells all of these products."
          }
        >
          <select
            id="po-supplier"
            className={inputClass(false)}
            value={supplierId}
            onChange={(event) => {
              setSupplierId(Number(event.target.value));
              setServerError(null);
            }}
            disabled={otherSuppliers.length <= 1}
          >
            {otherSuppliers.map((supplier) => (
              <option key={supplier.id} value={supplier.id}>
                {supplier.name} · {supplier.lead_time_days} day{supplier.lead_time_days === 1 ? "" : "s"} · {formatRM(supplier.total)}
              </option>
            ))}
          </select>
        </FormField>

        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Product</th>
                <th className="px-3 py-2 text-right font-medium">In stock</th>
                <th className="px-3 py-2 text-right font-medium">Suggested</th>
                <th className="px-3 py-2 font-medium">Order qty</th>
                <th className="px-3 py-2 text-right font-medium">Price</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {order.lines.map((line) => (
                <tr key={line.id}>
                  <td className="px-3 py-2">
                    <p className="font-medium text-slate-900">{line.item_name}</p>
                    <p className="text-xs text-slate-500">
                      {line.sku} · reorder at {line.reorder_threshold}
                    </p>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                    {line.current_quantity} <span className="text-slate-500">{line.unit}</span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">{line.recommended_quantity}</td>
                  <td className="px-3 py-2">
                    <input
                      aria-label={`Order quantity for ${line.item_name}`}
                      inputMode="numeric"
                      className={`${inputClass(Boolean(lineErrors[line.id]))} w-24`}
                      value={quantities[line.id] ?? ""}
                      onChange={(event) => {
                        setQuantities((current) => ({ ...current, [line.id]: event.target.value }));
                        setServerError(null);
                      }}
                    />
                    {lineErrors[line.id] && <p className="mt-1 text-xs text-red-600">{lineErrors[line.id]}</p>}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{formatRM(line.unit_price)}</td>
                  <td className="px-3 py-2 text-right">
                    {order.lines.length > 1 && (
                      <button
                        type="button"
                        onClick={() => handleRemove(line)}
                        disabled={saving}
                        className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                      >
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="-mt-3 text-xs text-slate-500">Removing a product takes effect immediately. Other edits are saved with the button below.</p>

        <FormField label="Note for the supplier (optional)" htmlFor="po-notes">
          <textarea
            id="po-notes"
            rows={2}
            maxLength={500}
            className={inputClass(false)}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </FormField>

        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3 text-sm">
          <span className="text-slate-600">{supplierChanged ? "Total at the new supplier" : "Estimated total"}</span>
          <span className="font-semibold text-slate-900">
            {supplierChanged
              ? formatRM(otherSuppliers.find((supplier) => supplier.id === supplierId)?.total)
              : formatRM(previewTotal)}
          </span>
        </div>
        {supplierChanged && (
          <p className="-mt-3 text-xs text-slate-500">Based on the quantities already saved. The final total is shown after saving.</p>
        )}

        <div className="flex justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Close
          </button>
          <button
            type="submit"
            disabled={saving || !hasChanges || hasLineErrors}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
