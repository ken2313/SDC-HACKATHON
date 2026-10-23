import { useState } from "react";
import { purchaseOrdersApi } from "../api/purchaseOrders.js";
import { formatRM } from "../utils/money.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";

// Owner-only. A reason is required so the activity log explains the decision.
export default function RejectOrderModal({ order, onClose, onRejected }) {
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
      await purchaseOrdersApi.reject(order.id, trimmed);
      onRejected();
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  return (
    <Modal
      title={`Reject ${order.po_number}`}
      subtitle={`${order.supplier.name} · ${formatRM(order.total)}`}
      onClose={onClose}
      busy={saving}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}
        <p className="text-sm text-slate-600">
          Nothing will be ordered. The products on this order become free again, so a new draft can be prepared if they are still low.
        </p>
        <FormField
          label="Reason for rejecting"
          htmlFor="reject-reason"
          error={reason !== "" && !valid ? "Please write at least 3 characters." : null}
          hint="This reason is saved in the activity log."
        >
          <textarea
            id="reject-reason"
            rows={3}
            maxLength={500}
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
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || !valid}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Rejecting…" : "Reject order"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
