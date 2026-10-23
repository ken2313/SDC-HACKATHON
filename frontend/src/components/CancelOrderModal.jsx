import { useState } from "react";
import { supplierOrdersApi } from "../api/supplierOrders.js";
import { formatRM } from "../utils/money.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";

// Owner only. A reason is required so the activity log explains why.
export default function CancelOrderModal({ order, onClose, onCancelled }) {
  const [reason, setReason] = useState("");
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);

  const trimmed = reason.trim();
  const valid = trimmed.length >= 3;

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || !valid) return;
    setSaving(true);
    setServerError(null);
    try {
      await supplierOrdersApi.cancel(order.id, trimmed);
      onCancelled();
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  return (
    <Modal title={`Cancel ${order.po_number}`} subtitle={`${order.supplier_name} · ${formatRM(order.total)}`} onClose={onClose} busy={saving}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}
        <p className="text-sm text-slate-600">
          Stock is not changed. The products become free again, so a new draft can be prepared if they are still low. Cancelling cannot be undone.
        </p>
        <FormField
          label="Reason for cancelling"
          htmlFor="cancel-reason"
          error={reason !== "" && !valid ? "Please write at least 3 characters." : null}
          hint="This reason is saved in the activity log."
        >
          <textarea
            id="cancel-reason"
            rows={3}
            maxLength={255}
            className={inputClass(reason !== "" && !valid)}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
              setServerError(null);
            }}
            autoFocus
          />
        </FormField>
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Keep order
          </button>
          <button
            type="submit"
            disabled={saving || !valid}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Cancelling…" : "Cancel order"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
