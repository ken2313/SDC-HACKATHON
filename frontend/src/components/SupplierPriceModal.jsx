import { useEffect, useState } from "react";
import { inventoryApi } from "../api/inventory.js";
import { suppliersApi } from "../api/suppliers.js";
import { formatRM } from "../utils/money.js";
import FormField, { inputClass } from "./FormField.jsx";
import Modal from "./Modal.jsx";
import Spinner from "./Spinner.jsx";

const PRICE_PATTERN = /^\d+(\.\d{1,2})?$/; // RM, at most 2 decimals (whole sen)

// Add a product to a supplier's price list (line = null) or change a price (line = existing entry).
// `preselectItemId` opens the form with a product already chosen (from "Products without a supplier").
export default function SupplierPriceModal({ supplier, line, preselectItemId = null, onClose, onSaved }) {
  const isEdit = Boolean(line);
  const [products, setProducts] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [values, setValues] = useState({
    item_id: preselectItemId ? String(preselectItemId) : "",
    unit_price: line ? line.unit_price.toFixed(2) : "",
    min_order_qty: String(line?.min_order_qty ?? 1),
  });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [saving, setSaving] = useState(false);

  // Products that can be added: active products that are not on this price list yet
  useEffect(() => {
    if (isEdit) return undefined;
    let cancelled = false;
    inventoryApi
      .list({ sort_by: "name" })
      .then((items) => {
        if (cancelled) return;
        const listed = new Set(supplier.products.map((p) => p.item_id));
        setProducts(items.filter((item) => !listed.has(item.id)));
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message);
      });
    return () => {
      cancelled = true;
    };
  }, [isEdit, supplier.products]);

  function setField(field, value) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  function validate() {
    const found = {};
    if (!isEdit && !values.item_id) found.item_id = "Choose a product.";
    const price = values.unit_price.trim();
    if (!PRICE_PATTERN.test(price)) found.unit_price = "Enter a price in RM, for example 7.80.";
    else if (Number(price) > 100000) found.unit_price = "That price looks too high (max RM 100,000).";
    if (!/^\d+$/.test(values.min_order_qty.trim()) || Number(values.min_order_qty) < 1) {
      found.min_order_qty = "Enter a whole number, 1 or more.";
    }
    return found;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    const unitPrice = Number(values.unit_price.trim());
    const minOrder = Number(values.min_order_qty.trim());
    setSaving(true);
    setServerError(null);
    try {
      if (isEdit) {
        const updated = await suppliersApi.updateProduct(supplier.id, line.id, {
          unit_price: unitPrice,
          min_order_qty: minOrder,
        });
        onSaved({ supplier: updated, draft_purchase_order: null }, isEdit);
      } else {
        const result = await suppliersApi.addProduct(supplier.id, {
          item_id: Number(values.item_id),
          unit_price: unitPrice,
          min_order_qty: minOrder,
        });
        onSaved(result, isEdit);
      }
    } catch (error) {
      setServerError(error.message);
      setSaving(false);
    }
  }

  const chosen = products?.find((item) => String(item.id) === values.item_id);
  const unit = isEdit ? line.unit : chosen?.unit;

  return (
    <Modal
      title={isEdit ? "Change price" : "Add product to price list"}
      subtitle={isEdit ? `${line.item_name} from ${supplier.name}` : supplier.name}
      onClose={onClose}
      busy={saving}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {serverError}
          </div>
        )}

        {!isEdit &&
          (loadError ? (
            <p role="alert" className="text-sm text-red-600">{loadError}</p>
          ) : products === null ? (
            <Spinner label="Loading products…" className="py-4" />
          ) : products.length === 0 ? (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
              Every active product is already on this price list.
            </p>
          ) : (
            <FormField label="Product" htmlFor="sp-item" error={errors.item_id}>
              <select
                id="sp-item"
                className={inputClass(errors.item_id)}
                value={values.item_id}
                onChange={(e) => setField("item_id", e.target.value)}
              >
                <option value="">Choose a product…</option>
                {products.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ({item.sku})
                  </option>
                ))}
              </select>
            </FormField>
          ))}

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Unit price (RM)"
            htmlFor="sp-price"
            error={errors.unit_price}
            hint={
              isEdit
                ? `Now ${formatRM(line.unit_price)} per ${unit}. Orders already prepared keep their price.`
                : `Price for one ${unit ? `unit (${unit})` : "unit"}.`
            }
          >
            <input
              id="sp-price"
              inputMode="decimal"
              className={inputClass(errors.unit_price)}
              value={values.unit_price}
              onChange={(e) => setField("unit_price", e.target.value)}
              placeholder="7.80"
              autoFocus={isEdit}
            />
          </FormField>
          <FormField
            label="Minimum order"
            htmlFor="sp-min"
            error={errors.min_order_qty}
            hint="Drafts never order less than this."
          >
            <input
              id="sp-min"
              inputMode="numeric"
              className={inputClass(errors.min_order_qty)}
              value={values.min_order_qty}
              onChange={(e) => setField("min_order_qty", e.target.value)}
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
            disabled={saving || (!isEdit && (!products || products.length === 0))}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {saving ? "Saving…" : isEdit ? "Save price" : "Add to price list"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
