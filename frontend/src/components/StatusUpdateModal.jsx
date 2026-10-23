import { useState } from "react";
import { supplierOrdersApi } from "../api/supplierOrders.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";

function todayLocal() {
  return new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD
}

// Mark an order Shipped or Delayed. A delayed order needs a new expected date.
export default function StatusUpdateModal({ order, status, onClose, onSaved }) {
  const delaying = status === "delayed";
  const [date, setDate] = useState(order.estimated_delivery_date && !order.is_overdue ? order.estimated_delivery_date : "");
  const [note, setNote] = useState("");
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);

  const dateMissing = delaying && !date;
  const datePast = date !== "" && date < todayLocal();
  const valid = !dateMissing && !datePast;

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || !valid) return;
    setSaving(true);
    setServerError(null);
    try {
      const updated = await supplierOrdersApi.updateStatus(order.id, {
        status,
        estimated_delivery_date: date || null,
        note: note.trim() || null,
      });
      onSaved(updated);
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  return (
    <Modal
      title={delaying ? `Mark ${order.po_number} as delayed` : `Mark ${order.po_number} as shipped`}
      subtitle={order.supplier_name}
      onClose={onClose}
      busy={saving}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}
        <FormField
          label={delaying ? "New expected delivery date" : "Expected delivery date (optional)"}
          htmlFor="status-date"
          error={datePast ? "The date cannot be in the past." : dateMissing ? "Enter the new expected date." : null}
        >
          <input
            id="status-date"
            type="date"
            min={todayLocal()}
            className={inputClass(datePast)}
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </FormField>
        <FormField label="Note (optional)" htmlFor="status-note" hint="For example what the supplier told you. Saved in the order timeline.">
          <input
            id="status-note"
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
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : delaying ? "Mark delayed" : "Mark shipped"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
