import { useState } from "react";
import { supplierOrdersApi } from "../api/supplierOrders.js";
import { isWholeNumber } from "../utils/stock.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";

// Confirm what REALLY arrived. This adds stock to the inventory, once, and cannot be repeated.
export default function ReceiveDeliveryModal({ order, onClose, onReceived }) {
  const [quantities, setQuantities] = useState(() =>
    Object.fromEntries(order.lines.map((line) => [line.id, String(line.quantity_ordered)]))
  );
  const [note, setNote] = useState("");
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);

  const allWhole = order.lines.every((line) => isWholeNumber(quantities[line.id]));
  const receivedTotal = allWhole ? order.lines.reduce((sum, line) => sum + Number(quantities[line.id]), 0) : 0;
  const orderedTotal = order.lines.reduce((sum, line) => sum + line.quantity_ordered, 0);
  const valid = allWhole && receivedTotal >= 1;
  const short = valid && receivedTotal < orderedTotal;

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || !valid) return;
    setSaving(true);
    setServerError(null);
    try {
      const result = await supplierOrdersApi.receive(order.id, {
        lines: order.lines.map((line) => ({ line_id: line.id, received_quantity: Number(quantities[line.id]) })),
        note: note.trim() || null,
      });
      onReceived(result);
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  return (
    <Modal title={`Confirm delivery of ${order.po_number}`} subtitle={order.supplier_name} onClose={onClose} busy={saving} size="lg">
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}
        <p className="text-sm text-slate-600">
          Enter how many of each product actually arrived. Stock is increased by these amounts. This can only be done once for an order.
        </p>
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Product</th>
                <th className="px-3 py-2 text-right font-medium">Ordered</th>
                <th className="px-3 py-2 font-medium">Received</th>
              </tr>
            </thead>
            <tbody>
              {order.lines.map((line) => {
                const text = quantities[line.id];
                const bad = text !== "" && !isWholeNumber(text);
                return (
                  <tr key={line.id} className="border-t border-slate-100">
                    <td className="px-3 py-2">
                      <p className="font-medium text-slate-900">{line.item_name}</p>
                      <p className="text-xs text-slate-500">{line.sku}</p>
                    </td>
                    <td className="px-3 py-2 text-right text-slate-700">
                      {line.quantity_ordered} {line.unit}
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        inputMode="numeric"
                        aria-label={`Received quantity for ${line.item_name}`}
                        className={`${inputClass(bad)} w-24`}
                        value={text}
                        onChange={(event) => {
                          setQuantities((current) => ({ ...current, [line.id]: event.target.value }));
                          setServerError(null);
                        }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!allWhole && <p className="text-xs text-red-600">Use whole numbers (0 or more) for every product.</p>}
        {allWhole && receivedTotal < 1 && <p className="text-xs text-red-600">Enter at least one received item.</p>}
        {short && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Short delivery: {receivedTotal} of {orderedTotal} items. If a product is still low afterwards, the system prepares a new draft order for the owner to review.
          </p>
        )}
        <FormField label="Note (optional)" htmlFor="receive-note" hint="For example the delivery note number.">
          <input
            id="receive-note"
            type="text"
            maxLength={255}
            className={inputClass(false)}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </FormField>
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || !valid}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Updating stock…" : "Confirm delivery and update stock"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
