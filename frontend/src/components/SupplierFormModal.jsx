import { useState } from "react";
import { suppliersApi } from "../api/suppliers.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";

// Same simple rules as the backend (the backend checks again).
const PHONE_PATTERN = /^\+?[0-9][0-9 ()-]{5,38}$/;
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function validate(values) {
  const errors = {};
  if (!values.name.trim()) errors.name = "Supplier name is required.";
  const phone = values.phone.trim();
  if (phone && !PHONE_PATTERN.test(phone)) errors.phone = "Use digits, spaces, '+', '-' or brackets (e.g. +60 3-5555 0101).";
  const email = values.email.trim();
  if (email && !EMAIL_PATTERN.test(email)) errors.email = "Enter a valid email address.";
  const lead = values.lead_time_days.trim();
  if (!/^\d+$/.test(lead) || Number(lead) > 365) errors.lead_time_days = "Enter whole days, 0 to 365.";
  return errors;
}

const FIELDS = ["name", "contact_name", "phone", "email", "address", "notes"];

// Add a supplier (supplier = null) or edit one (supplier = existing record).
export default function SupplierFormModal({ supplier, onClose, onSaved }) {
  const isEdit = Boolean(supplier);
  const [values, setValues] = useState({
    name: supplier?.name ?? "",
    contact_name: supplier?.contact_name ?? "",
    phone: supplier?.phone ?? "",
    email: supplier?.email ?? "",
    address: supplier?.address ?? "",
    notes: supplier?.notes ?? "",
    lead_time_days: String(supplier?.lead_time_days ?? 3),
  });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);

  function setField(field, value) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const found = validate(values);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const payload = { lead_time_days: Number(values.lead_time_days) };
    FIELDS.forEach((field) => {
      payload[field] = values[field].trim() || null;
    });

    setSaving(true);
    setServerError(null);
    try {
      const saved = isEdit ? await suppliersApi.update(supplier.id, payload) : await suppliersApi.create(payload);
      onSaved(saved, isEdit);
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  return (
    <Modal
      title={isEdit ? "Edit supplier" : "Add supplier"}
      subtitle={isEdit ? supplier.name : "Contact details and usual delivery time. Prices are added after saving."}
      onClose={onClose}
      busy={saving}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}

        <FormField label="Supplier name" htmlFor="sf-name" error={errors.name}>
          <input
            id="sf-name"
            className={inputClass(errors.name)}
            value={values.name}
            maxLength={120}
            onChange={(e) => setField("name", e.target.value)}
            placeholder="e.g. Segar Dairy Sdn Bhd"
            autoFocus
          />
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Contact person (optional)" htmlFor="sf-contact">
            <input
              id="sf-contact"
              className={inputClass(false)}
              value={values.contact_name}
              maxLength={120}
              onChange={(e) => setField("contact_name", e.target.value)}
              placeholder="e.g. Lim Wei Jie"
            />
          </FormField>
          <FormField
            label="Typical delivery time (days)"
            htmlFor="sf-lead"
            error={errors.lead_time_days}
            hint="Used for expected delivery dates. 0 = same day."
          >
            <input
              id="sf-lead"
              inputMode="numeric"
              className={inputClass(errors.lead_time_days)}
              value={values.lead_time_days}
              onChange={(e) => setField("lead_time_days", e.target.value)}
            />
          </FormField>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Phone (optional)" htmlFor="sf-phone" error={errors.phone}>
            <input
              id="sf-phone"
              type="tel"
              className={inputClass(errors.phone)}
              value={values.phone}
              maxLength={40}
              onChange={(e) => setField("phone", e.target.value)}
              placeholder="+60 3-5555 0101"
            />
          </FormField>
          <FormField label="Email (optional)" htmlFor="sf-email" error={errors.email}>
            <input
              id="sf-email"
              type="email"
              className={inputClass(errors.email)}
              value={values.email}
              maxLength={160}
              onChange={(e) => setField("email", e.target.value)}
              placeholder="orders@supplier.example"
            />
          </FormField>
        </div>

        <FormField label="Address (optional)" htmlFor="sf-address">
          <input
            id="sf-address"
            className={inputClass(false)}
            value={values.address}
            maxLength={255}
            onChange={(e) => setField("address", e.target.value)}
            placeholder="Lot 12, Jalan Industri 3, Shah Alam, Selangor"
          />
        </FormField>

        <FormField label="Notes (optional)" htmlFor="sf-notes" hint="For example delivery days or payment terms.">
          <textarea
            id="sf-notes"
            rows={2}
            className={inputClass(false)}
            value={values.notes}
            maxLength={500}
            onChange={(e) => setField("notes", e.target.value)}
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
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {saving ? "Saving…" : isEdit ? "Save changes" : "Add supplier"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
