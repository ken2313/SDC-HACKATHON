import { useEffect, useState } from "react";
import { inventoryApi } from "../api/inventory.js";
import { suppliersApi } from "../api/suppliers.js";
import { isWholeNumber } from "../utils/stock.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";

const SKU_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/;

function validate(values, isEdit) {
  const errors = {};
  if (!values.name.trim()) errors.name = "Product name is required.";
  if (!values.sku.trim()) errors.sku = "SKU is required.";
  else if (!SKU_PATTERN.test(values.sku.trim())) errors.sku = "Use letters, numbers, '-' or '_' only (no spaces).";
  if (!values.category.trim()) errors.category = "Category is required.";
  if (!values.unit.trim()) errors.unit = "Unit is required (for example: cartons, packs).";
  if (!isEdit && !isWholeNumber(values.quantity)) errors.quantity = "Enter a whole number, 0 or more.";
  if (!isWholeNumber(values.reorder_threshold)) errors.reorder_threshold = "Enter a whole number, 0 or more.";
  return errors;
}

// Add a product (product = null) or edit one (product = existing item).
export default function ProductFormModal({ product, categories, onClose, onSaved }) {
  const isEdit = Boolean(product);
  const [values, setValues] = useState({
    name: product?.name ?? "",
    sku: product?.sku ?? "",
    category: product?.category ?? "",
    unit: product?.unit ?? "pcs",
    supplier_name: product?.supplier_name ?? "",
    quantity: "0",
    reorder_threshold: String(product?.reorder_threshold ?? 0),
  });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [supplierNames, setSupplierNames] = useState([]);

  // Feature 6: suggest the business's active suppliers (typing another name is still allowed)
  useEffect(() => {
    let cancelled = false;
    suppliersApi
      .list()
      .then((rows) => {
        if (!cancelled) setSupplierNames(rows.map((row) => row.name));
      })
      .catch(() => {
        /* suggestions are optional: the field still works without them */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function setField(field, value) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;

    const found = validate(values, isEdit);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const payload = {
      name: values.name.trim(),
      sku: values.sku.trim(),
      category: values.category.trim(),
      unit: values.unit.trim(),
      supplier_name: values.supplier_name.trim() || null,
      reorder_threshold: Number(values.reorder_threshold),
    };

    setSaving(true);
    setServerError(null);
    try {
      const saved = isEdit
        ? await inventoryApi.update(product.id, payload)
        : await inventoryApi.create({ ...payload, quantity: Number(values.quantity) });
      onSaved(saved, isEdit);
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  return (
    <Modal
      title={isEdit ? "Edit product" : "Add product"}
      subtitle={isEdit ? product.name : "Create a new item in your inventory."}
      onClose={onClose}
      busy={saving}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}

        <FormField label="Product name" htmlFor="pf-name" error={errors.name}>
          <input
            id="pf-name"
            className={inputClass(errors.name)}
            value={values.name}
            maxLength={120}
            onChange={(e) => setField("name", e.target.value)}
            placeholder="e.g. Fresh Milk 1L"
            autoFocus
          />
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="SKU" htmlFor="pf-sku" error={errors.sku} hint="Unique code per product. Saved in capitals.">
            <input
              id="pf-sku"
              className={inputClass(errors.sku)}
              value={values.sku}
              maxLength={40}
              onChange={(e) => setField("sku", e.target.value)}
              placeholder="e.g. MILK-1L"
            />
          </FormField>
          <FormField label="Category" htmlFor="pf-category" error={errors.category}>
            <input
              id="pf-category"
              list="pf-category-options"
              className={inputClass(errors.category)}
              value={values.category}
              maxLength={60}
              onChange={(e) => setField("category", e.target.value)}
              placeholder="e.g. Dairy"
            />
            <datalist id="pf-category-options">
              {categories.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </FormField>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Unit" htmlFor="pf-unit" error={errors.unit}>
            <input
              id="pf-unit"
              className={inputClass(errors.unit)}
              value={values.unit}
              maxLength={20}
              onChange={(e) => setField("unit", e.target.value)}
              placeholder="cartons, packs, bags…"
            />
          </FormField>
          <FormField
            label="Supplier (optional)"
            htmlFor="pf-supplier"
            hint="A label shown in Inventory. Prices for ordering are set on the Suppliers page."
          >
            <input
              id="pf-supplier"
              list="pf-supplier-options"
              className={inputClass(false)}
              value={values.supplier_name}
              maxLength={120}
              onChange={(e) => setField("supplier_name", e.target.value)}
              placeholder="e.g. Segar Dairy Sdn Bhd (demo)"
            />
            <datalist id="pf-supplier-options">
              {supplierNames.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </FormField>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {isEdit ? (
            <FormField label="Current quantity" htmlFor="pf-qty-readonly" hint="Change quantity with the Stock button so it is recorded.">
              <input id="pf-qty-readonly" className={inputClass(false)} value={`${product.quantity} ${product.unit}`} disabled readOnly />
            </FormField>
          ) : (
            <FormField label="Opening quantity" htmlFor="pf-qty" error={errors.quantity}>
              <input
                id="pf-qty"
                inputMode="numeric"
                className={inputClass(errors.quantity)}
                value={values.quantity}
                onChange={(e) => setField("quantity", e.target.value)}
              />
            </FormField>
          )}
          <FormField
            label="Reorder threshold"
            htmlFor="pf-threshold"
            error={errors.reorder_threshold}
            hint="Low Stock starts when quantity reaches this number."
          >
            <input
              id="pf-threshold"
              inputMode="numeric"
              className={inputClass(errors.reorder_threshold)}
              value={values.reorder_threshold}
              onChange={(e) => setField("reorder_threshold", e.target.value)}
            />
          </FormField>
        </div>

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
            {saving ? "Saving…" : isEdit ? "Save changes" : "Add product"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
