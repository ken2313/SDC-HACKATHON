import { useRef, useState } from "react";
import { inventoryApi } from "../api/inventory.js";
import { computeStatus, isWholeNumber, newRequestId } from "../utils/stock.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";
import StatusBadge from "./StatusBadge.jsx";

// Add or remove stock. A unique request id is sent with every attempt, so a
// double click or a network retry can never change the stock twice.
export default function StockMovementModal({ item, onClose, onSaved }) {
  const [type, setType] = useState("out");
  const [quantityText, setQuantityText] = useState("");
  const [reason, setReason] = useState("");
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);
  const requestIdRef = useRef(newRequestId());

  // If the person changes the form, it is a NEW request and gets a new id.
  function touch() {
    requestIdRef.current = newRequestId();
    setServerError(null);
  }

  const validNumber = isWholeNumber(quantityText) && Number(quantityText) >= 1;
  const amount = validNumber ? Number(quantityText) : 0;
  const tooMuch = type === "out" && amount > item.quantity;
  const newQuantity = item.quantity + (type === "in" ? amount : -amount);

  let fieldError = null;
  if (quantityText !== "" && !validNumber) fieldError = "Enter a whole number of 1 or more.";
  else if (tooMuch) fieldError = `Only ${item.quantity} ${item.unit} available. You cannot remove more than that.`;

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving || !validNumber || tooMuch) return;

    setSaving(true);
    setServerError(null);
    try {
      const result = await inventoryApi.recordMovement(item.id, {
        movement_type: type,
        quantity: amount,
        reason: reason.trim() || null,
        request_id: requestIdRef.current,
      });
      onSaved(result);
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  return (
    <Modal title="Update stock" subtitle={`${item.name} · ${item.sku}`} onClose={onClose} busy={saving}>
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

        <fieldset>
          <legend className="mb-1 block text-sm font-medium text-slate-700">What happened?</legend>
          <div className="grid grid-cols-2 gap-2">
            {[
              ["out", "Remove stock"],
              ["in", "Add stock"],
            ].map(([value, label]) => (
              <label
                key={value}
                className={`cursor-pointer rounded-lg border px-3 py-2 text-center text-sm font-medium ${
                  type === value
                    ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                    : "border-slate-300 text-slate-600 hover:bg-slate-50"
                }`}
              >
                <input
                  type="radio"
                  name="movement-type"
                  value={value}
                  checked={type === value}
                  onChange={() => {
                    setType(value);
                    touch();
                  }}
                  className="sr-only"
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>

        <FormField label={`Quantity (${item.unit})`} htmlFor="sm-qty" error={fieldError}>
          <input
            id="sm-qty"
            inputMode="numeric"
            className={inputClass(fieldError)}
            value={quantityText}
            onChange={(e) => {
              setQuantityText(e.target.value);
              touch();
            }}
            placeholder="e.g. 15"
            autoFocus
          />
        </FormField>

        <FormField label="Reason (optional)" htmlFor="sm-reason">
          <input
            id="sm-reason"
            className={inputClass(false)}
            value={reason}
            maxLength={255}
            onChange={(e) => {
              setReason(e.target.value);
              touch();
            }}
            placeholder={type === "out" ? "e.g. Used during weekend rush" : "e.g. Delivery received"}
          />
        </FormField>

        {validNumber && !tooMuch && (
          <div className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-3 text-sm">
            <span className="text-slate-600">
              New stock:{" "}
              <strong className="text-slate-900">
                {newQuantity} {item.unit}
              </strong>
            </span>
            <StatusBadge status={computeStatus(newQuantity, item.reorder_threshold)} />
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
            disabled={saving || !validNumber || tooMuch}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : type === "out" ? "Remove stock" : "Add stock"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
