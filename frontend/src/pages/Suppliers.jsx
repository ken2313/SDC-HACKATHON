import { useCallback, useEffect, useRef, useState } from "react";
import { suppliersApi } from "../api/suppliers.js";
import Spinner from "../components/Spinner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import SupplierDetailModal from "../components/SupplierDetailModal.jsx";
import SupplierFormModal from "../components/SupplierFormModal.jsx";
import SupplierPriceModal from "../components/SupplierPriceModal.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { formatRM } from "../utils/money.js";

const PERM_MANAGE = "suppliers:manage";

function SummaryCard({ label, value, tone = "text-slate-900", hint }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" title={hint}>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value ?? "–"}</p>
    </div>
  );
}

// Products nobody sells cannot get a purchase order draft. Show them so the owner can fix it.
function MissingSuppliers({ products, activeSuppliers, canManage, onAddPrice }) {
  const [choice, setChoice] = useState({});
  if (products.length === 0) return null;
  const lowCount = products.filter((p) => p.stock_status !== "in_stock").length;

  return (
    <section className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
      <h2 className="text-sm font-semibold text-amber-900">
        {products.length} product{products.length === 1 ? " has" : "s have"} no supplier price
        {lowCount > 0 && <span className="text-red-700"> ({lowCount} low right now)</span>}
      </h2>
      <p className="mt-0.5 text-sm text-amber-800">
        The system cannot prepare purchase orders for these until an active supplier has a price for them.
      </p>
      <ul className="mt-3 divide-y divide-amber-200/70">
        {products.map((product) => (
          <li key={product.item_id} className="flex flex-wrap items-center justify-between gap-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-900">{product.item_name}</span>
              <span className="text-xs text-slate-500">{product.sku}</span>
              <StatusBadge status={product.stock_status} />
              <span className="text-xs text-slate-500">
                {product.quantity} {product.unit}, reorder at {product.reorder_threshold}
              </span>
            </div>
            {canManage && activeSuppliers.length > 0 && (
              <div className="flex items-center gap-2">
                <label htmlFor={`missing-${product.item_id}`} className="sr-only">Supplier for {product.item_name}</label>
                <select
                  id={`missing-${product.item_id}`}
                  value={choice[product.item_id] ?? ""}
                  onChange={(e) => setChoice((current) => ({ ...current, [product.item_id]: e.target.value }))}
                  className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
                >
                  <option value="">Choose supplier…</option>
                  {activeSuppliers.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={!choice[product.item_id]}
                  onClick={() => onAddPrice(Number(choice[product.item_id]), product.item_id)}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  Add price
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {!canManage && <p className="mt-2 text-xs text-amber-800">Ask the owner to add a supplier price.</p>}
    </section>
  );
}

export default function Suppliers() {
  const { can, business } = useSession();
  const toast = useToast();
  const canManage = can(PERM_MANAGE);

  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [missing, setMissing] = useState([]);
  const [activeSuppliers, setActiveSuppliers] = useState([]); // for the "Add price" choice, not affected by search
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState(null);
  const [quickPrice, setQuickPrice] = useState(null); // { supplier, itemId }

  const latestRequest = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const load = useCallback(async () => {
    const requestNumber = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const [list, counts, without, active] = await Promise.all([
        suppliersApi.list({ include_inactive: showInactive, search: debouncedSearch }),
        suppliersApi.summary(),
        suppliersApi.withoutSupplier(),
        suppliersApi.list(),
      ]);
      if (requestNumber !== latestRequest.current) return;
      setRows(list);
      setSummary(counts);
      setMissing(without);
      setActiveSuppliers(active);
    } catch (err) {
      if (requestNumber !== latestRequest.current) return;
      setError(err.message);
    } finally {
      if (requestNumber === latestRequest.current) setLoading(false);
    }
  }, [showInactive, debouncedSearch]);

  useEffect(() => {
    load();
  }, [load]);

  function handleCreated(created) {
    setAdding(false);
    toast.success(`${created.name} was added. Now add the products it sells.`);
    load();
    setOpenId(created.id);
  }

  async function startQuickPrice(supplierId, itemId) {
    try {
      // The price form needs the supplier's current price list
      const supplier = await suppliersApi.get(supplierId);
      setQuickPrice({ supplier, itemId });
    } catch (err) {
      toast.error(err.message);
    }
  }

  function handleQuickPriceSaved(result) {
    setQuickPrice(null);
    const draft = result.draft_purchase_order;
    toast.success(
      draft
        ? `Price added. The product is low, so draft ${draft.po_number} was prepared for the owner to approve.`
        : `Price added to ${result.supplier.name}'s price list.`
    );
    load();
  }

  const filtered = Boolean(debouncedSearch);
  const showEmpty = !loading && !error && rows.length === 0;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Suppliers</h1>
          <p className="text-sm text-slate-500">
            Contacts, prices and delivery times for {business.name}. Purchase order drafts use the cheapest active supplier.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          {canManage && (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
            >
              Add supplier
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryCard
          label="Active suppliers"
          value={summary?.active}
          hint={summary?.inactive ? `${summary.inactive} inactive` : undefined}
        />
        <SummaryCard label="Products covered" value={summary?.products_with_supplier} tone="text-emerald-600" hint="Active products at least one active supplier sells" />
        <SummaryCard
          label="No supplier"
          value={summary?.products_without_supplier}
          tone={summary?.low_without_supplier > 0 ? "text-red-600" : "text-slate-900"}
          hint="Active products nobody sells: they cannot be reordered"
        />
        <SummaryCard
          label="Avg delivery time"
          value={summary?.average_lead_time_days === null || summary?.average_lead_time_days === undefined ? "–" : `${summary.average_lead_time_days} days`}
          hint="Average of the active suppliers' usual delivery times"
        />
      </div>

      <MissingSuppliers products={missing} activeSuppliers={activeSuppliers} canManage={canManage} onAddPrice={startQuickPrice} />

      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="supplier-search" className="sr-only">Search suppliers</label>
        <input
          id="supplier-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name, contact, phone or email…"
          className="w-full max-w-sm rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
        />
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} className="rounded border-slate-300" />
          Show inactive suppliers
        </label>
      </div>

      {error && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error}</span>
          <button type="button" onClick={load} className="font-medium underline">Try again</button>
        </div>
      )}

      {loading && rows.length === 0 ? (
        <Spinner label="Loading suppliers…" />
      ) : showEmpty ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <p className="font-medium text-slate-900">{filtered ? "No supplier matches your search" : "No suppliers yet"}</p>
          <p className="mt-1 text-sm text-slate-500">
            {filtered
              ? "Try another name, or tick “Show inactive suppliers”."
              : canManage
                ? "Add your first supplier, then add the products it sells and their prices."
                : "The owner adds suppliers and their prices."}
          </p>
        </div>
      ) : (
        <div className={`overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm ${loading ? "opacity-60" : ""}`}>
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Supplier</th>
                <th className="hidden px-4 py-3 font-medium md:table-cell">Phone / email</th>
                <th className="px-4 py-3 text-right font-medium">Delivery</th>
                <th className="px-4 py-3 text-right font-medium">Products</th>
                <th className="hidden px-4 py-3 text-right font-medium sm:table-cell">Open orders</th>
                <th className="hidden px-4 py-3 text-right font-medium lg:table-cell">Received</th>
                <th className="px-4 py-3"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className={`border-t border-slate-100 ${row.is_active ? "" : "bg-slate-50/70 text-slate-500"}`}>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-slate-900">{row.name}</span>
                      {!row.is_active && (
                        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600">Inactive</span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500">{row.contact_name ?? "No contact person"}</p>
                  </td>
                  <td className="hidden px-4 py-3 text-slate-600 md:table-cell">
                    <p>{row.phone ?? "–"}</p>
                    <p className="text-xs text-slate-500">{row.email ?? ""}</p>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right text-slate-700">
                    {row.lead_time_days} day{row.lead_time_days === 1 ? "" : "s"}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-700">{row.product_count}</td>
                  <td className="hidden px-4 py-3 text-right text-slate-700 sm:table-cell">{row.open_orders}</td>
                  <td className="hidden whitespace-nowrap px-4 py-3 text-right text-slate-700 lg:table-cell">
                    {formatRM(row.delivered_value)}
                    <span className="block text-xs text-slate-500">
                      {row.delivered_orders} deliver{row.delivered_orders === 1 ? "y" : "ies"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => setOpenId(row.id)}
                      className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      {canManage ? "Manage" : "View"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!canManage && (
        <p className="text-xs text-slate-500">
          You can view suppliers and prices. Only the owner can add or edit suppliers and change prices.
        </p>
      )}

      {adding && <SupplierFormModal supplier={null} onClose={() => setAdding(false)} onSaved={handleCreated} />}
      {openId !== null && (
        <SupplierDetailModal supplierId={openId} canManage={canManage} onClose={() => setOpenId(null)} onChanged={load} />
      )}
      {quickPrice && (
        <SupplierPriceModal
          supplier={quickPrice.supplier}
          line={null}
          preselectItemId={quickPrice.itemId}
          onClose={() => setQuickPrice(null)}
          onSaved={handleQuickPriceSaved}
        />
      )}
    </div>
  );
}
