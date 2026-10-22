import { useState } from "react";
import { inventoryApi } from "../api/inventory.js";
import { computeStatus, isWholeNumber } from "../utils/stock.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";
import StatusBadge from "./StatusBadge.jsx";

// Owner-only: change the reorder threshold of one product.
// `item` needs: item_id, item_name, sku, unit, quantity, reorder_threshold.
export default function ThresholdModal({ item, onClose, onSaved }) {
  const [text, setText] = useState(String(item.reorder_threshold));
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);

  const valid = isWholeNumber(text);
  const newThreshold = valid ? Number(text) : null;
  const unchanged = valid && newThreshold === item.reorder_threshold;
  const newStatus = valid ? computeStatus(item.quantity, newThreshold) : null;
  const alertWillClose = valid && !unchanged && newStatus === "in_stock";

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || !valid || unchanged) return;
    setSaving(true);
    setServerError(null);
    try {
      await inventoryApi.update(item.item_id, { reorder_threshold: newThreshold });
      onSaved(newThreshold, newStatus);
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  return (
    <Modal title="Change reorder level" subtitle={`${item.item_name} · ${item.sku}`} onClose={onClose} busy={saving}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}

        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3 text-sm">
          <span className="text-slate-600">Current stock</span>
          <span className="font-semibold text-slate-900">
            {item.quantity} {item.unit}
          </span>
        </div>

        <FormField
          label={`Alert me when stock is at or below (${item.unit})`}
          htmlFor="th-value"
          error={text !== "" && !valid ? "Enter a whole number, 0 or more." : null}
          hint="Stock at this number or lower counts as Low Stock and triggers an alert."
        >
          <input
            id="th-value"
            inputMode="numeric"
            className={inputClass(text !== "" && !valid)}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setServerError(null);
            }}
            autoFocus
          />
        </FormField>

        {valid && !unchanged && (
          <div className="space-y-2 rounded-lg border border-slate-200 px-4 py-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-600">Status after the change</span>
              <StatusBadge status={newStatus} />
            </div>
            <p className="text-xs text-slate-500">
              {alertWillClose
                ? "This product will be above its reorder level, so its alert will be resolved."
                : "This product will still be at or below its reorder level, so an alert stays active."}
            </p>
          </div>
        )}

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
            disabled={saving || !valid || unchanged}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save reorder level"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
