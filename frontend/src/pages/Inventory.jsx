import { useCallback, useEffect, useRef, useState } from "react";
import { inventoryApi } from "../api/inventory.js";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import MovementHistoryModal from "../components/MovementHistoryModal.jsx";
import ProductFormModal from "../components/ProductFormModal.jsx";
import Spinner from "../components/Spinner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import StockMovementModal from "../components/StockMovementModal.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { useToast } from "../context/ToastContext.jsx";

const PERM_MANAGE = "inventory:manage";
const PERM_STOCK = "stock:record";

function SummaryCard({ label, value, tone }) {
  const tones = {
    neutral: "text-slate-900",
    green: "text-emerald-600",
    amber: "text-amber-600",
    red: "text-red-600",
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tones[tone]}`}>{value ?? "–"}</p>
    </div>
  );
}

function RowButton({ onClick, children, danger = false, primary = false }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-xs font-medium ${
        primary
          ? "bg-indigo-600 text-white hover:bg-indigo-700"
          : danger
          ? "text-red-600 hover:bg-red-50"
          : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {children}
    </button>
  );
}

function SortHeader({ label, column, sortBy, sortDir, onSort, className = "" }) {
  const active = sortBy === column;
  return (
    <th className={`px-4 py-3 font-medium ${className}`} aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort(column)} className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-slate-900">
        {label}
        <span className={active ? "text-indigo-600" : "text-slate-300"}>{active && sortDir === "desc" ? "▼" : "▲"}</span>
      </button>
    </th>
  );
}

export default function Inventory() {
  const { can, business, user } = useSession();
  const toast = useToast();

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [sortBy, setSortBy] = useState("name");
  const [sortDir, setSortDir] = useState("asc");

  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [formTarget, setFormTarget] = useState(undefined); // undefined = closed, null = new product, item = edit
  const [stockTarget, setStockTarget] = useState(null);
  const [historyTarget, setHistoryTarget] = useState(null);
  const [archiveTarget, setArchiveTarget] = useState(null);

  // Wait 300 ms after typing stops before searching
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Only the newest request is allowed to update the screen
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    const requestNumber = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const [list, counts, categoryList] = await Promise.all([
        inventoryApi.list({
          search: debouncedSearch,
          category,
          status,
          include_archived: includeArchived,
          sort_by: sortBy,
          sort_dir: sortDir,
        }),
        inventoryApi.summary(),
        inventoryApi.categories(),
      ]);
      if (requestNumber !== latestRequest.current) return;
      setItems(list);
      setSummary(counts);
      setCategories(categoryList);
    } catch (err) {
      if (requestNumber !== latestRequest.current) return;
      setError(err.message);
    } finally {
      if (requestNumber === latestRequest.current) setLoading(false);
    }
  }, [debouncedSearch, category, status, includeArchived, sortBy, sortDir]);

  useEffect(() => {
    load();
  }, [load]);

  function handleSort(column) {
    if (sortBy === column) {
      setSortDir((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDir("asc");
    }
  }

  function clearFilters() {
    setSearch("");
    setDebouncedSearch("");
    setCategory("");
    setStatus("");
    setIncludeArchived(false);
  }

  const filtersActive = Boolean(search || category || status || includeArchived);

  function handleProductSaved(saved, wasEdit) {
    setFormTarget(undefined);
    toast.success(wasEdit ? `Saved changes to ${saved.name}.` : `Added ${saved.name} to your inventory.`);
    load();
  }

  function handleStockSaved(result) {
    setStockTarget(null);
    const { movement, item, already_applied: alreadyApplied } = result;
    if (alreadyApplied) {
      toast.success(`That change was already recorded. ${item.name} stays at ${item.quantity} ${item.unit}.`);
    } else {
      const verb = movement.quantity_change > 0 ? "Added" : "Removed";
      const alertNote = item.stock_status === "in_stock" ? "" : " A low-stock alert is active (see Stock Alerts).";
      const draft = result.draft_purchase_order;
      const orderNote = draft ? ` Draft order ${draft.po_number} was prepared and is waiting for the owner's approval (see Purchase Orders).` : "";
      toast.success(`${verb} ${Math.abs(movement.quantity_change)} ${item.unit}. ${item.name} is now ${item.quantity} ${item.unit}.${alertNote}${orderNote}`);
    }
    load();
  }

  async function confirmArchive() {
    const target = archiveTarget;
    try {
      await inventoryApi.archive(target.id);
      toast.success(`Archived ${target.name}. You can restore it from "Show archived".`);
      setArchiveTarget(null);
      load();
    } catch (err) {
      toast.error(err.message);
      setArchiveTarget(null);
    }
  }

  async function restoreItem(item) {
    try {
      await inventoryApi.restore(item.id);
      toast.success(`Restored ${item.name}.`);
      load();
    } catch (err) {
      toast.error(err.message);
    }
  }

  const canManage = can(PERM_MANAGE);
  const canRecordStock = can(PERM_STOCK);
  const hasNoProductsAtAll = !loading && !error && items.length === 0 && !filtersActive;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Inventory</h1>
          <p className="text-sm text-slate-500">Products and stock levels for {business.name}.</p>
        </div>
        {canManage && (
          <button
            type="button"
            onClick={() => setFormTarget(null)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            + Add product
          </button>
        )}
      </div>

      {!canManage && (
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
          You are signed in as <strong>{user.name}</strong> (Employee). You can view products and record stock changes. Adding,
          editing and archiving products is for the Owner.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryCard label="Total products" value={summary?.total_products} tone="neutral" />
        <SummaryCard label="In stock" value={summary?.in_stock} tone="green" />
        <SummaryCard label="Low stock" value={summary?.low_stock} tone="amber" />
        <SummaryCard label="Out of stock" value={summary?.out_of_stock} tone="red" />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-4">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, SKU, category or supplier…"
            aria-label="Search products"
            className="min-w-[14rem] flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
          />
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            aria-label="Filter by category"
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">All categories</option>
            {categories.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label="Filter by stock status"
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            <option value="in_stock">In Stock</option>
            <option value="low_stock">Low Stock</option>
            <option value="out_of_stock">Out of Stock</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600"
            />
            Show archived
            {summary?.archived > 0 && <span className="text-slate-400">({summary.archived})</span>}
          </label>
          {filtersActive && (
            <button type="button" onClick={clearFilters} className="text-sm font-medium text-indigo-600 hover:text-indigo-800">
              Clear filters
            </button>
          )}
        </div>

        {error && (
          <div role="alert" className="m-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>Could not load inventory: {error}</span>
            <button type="button" onClick={load} className="rounded-md bg-white px-3 py-1 font-medium text-red-700 ring-1 ring-red-200 hover:bg-red-100">
              Try again
            </button>
          </div>
        )}

        {loading && items.length === 0 && !error && <Spinner label="Loading inventory…" />}

        {hasNoProductsAtAll && (
          <div className="px-4 py-16 text-center">
            <p className="text-base font-medium text-slate-900">No products yet</p>
            <p className="mt-1 text-sm text-slate-500">Add your first product to start tracking stock.</p>
            {canManage && (
              <button
                type="button"
                onClick={() => setFormTarget(null)}
                className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                + Add product
              </button>
            )}
          </div>
        )}

        {!loading && !error && items.length === 0 && filtersActive && (
          <div className="px-4 py-16 text-center">
            <p className="text-base font-medium text-slate-900">No products match your filters</p>
            <button type="button" onClick={clearFilters} className="mt-3 text-sm font-medium text-indigo-600 hover:text-indigo-800">
              Clear filters
            </button>
          </div>
        )}

        {items.length > 0 && (
          <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}>
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr>
                  <SortHeader label="Product" column="name" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                  <SortHeader label="Category" column="category" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="hidden md:table-cell" />
                  <th className="hidden px-4 py-3 font-medium uppercase tracking-wide lg:table-cell">Supplier</th>
                  <SortHeader label="Quantity" column="quantity" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="text-right" />
                  <th className="hidden px-4 py-3 text-right font-medium uppercase tracking-wide md:table-cell">Reorder at</th>
                  <th className="px-4 py-3 font-medium uppercase tracking-wide">Status</th>
                  <th className="px-4 py-3 text-right font-medium uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => (
                  <tr key={item.id} className={item.is_archived ? "bg-slate-50 text-slate-400" : "hover:bg-slate-50/60"}>
                    <td className="px-4 py-3">
                      <p className={`font-medium ${item.is_archived ? "text-slate-500" : "text-slate-900"}`}>
                        {item.name}
                        {item.is_archived && (
                          <span className="ml-2 rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-600">Archived</span>
                        )}
                      </p>
                      <p className="text-xs text-slate-500">{item.sku}</p>
                    </td>
                    <td className="hidden px-4 py-3 md:table-cell">{item.category}</td>
                    <td className="hidden px-4 py-3 lg:table-cell">{item.supplier_name ?? "—"}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-semibold tabular-nums">
                      {item.quantity} <span className="font-normal text-slate-500">{item.unit}</span>
                    </td>
                    <td className="hidden px-4 py-3 text-right tabular-nums md:table-cell">{item.reorder_threshold}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={item.stock_status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap justify-end gap-1">
                        {!item.is_archived && canRecordStock && (
                          <RowButton primary onClick={() => setStockTarget(item)}>
                            Stock
                          </RowButton>
                        )}
                        <RowButton onClick={() => setHistoryTarget(item)}>History</RowButton>
                        {!item.is_archived && canManage && <RowButton onClick={() => setFormTarget(item)}>Edit</RowButton>}
                        {!item.is_archived && canManage && (
                          <RowButton danger onClick={() => setArchiveTarget(item)}>
                            Archive
                          </RowButton>
                        )}
                        {item.is_archived && canManage && <RowButton onClick={() => restoreItem(item)}>Restore</RowButton>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {formTarget !== undefined && (
        <ProductFormModal
          product={formTarget}
          categories={categories}
          onClose={() => setFormTarget(undefined)}
          onSaved={handleProductSaved}
        />
      )}

      {stockTarget && <StockMovementModal item={stockTarget} onClose={() => setStockTarget(null)} onSaved={handleStockSaved} />}

      {historyTarget && <MovementHistoryModal item={historyTarget} onClose={() => setHistoryTarget(null)} />}

      {archiveTarget && (
        <ConfirmDialog
          title="Archive this product?"
          message={`${archiveTarget.name} will be hidden from the inventory list and cannot receive stock changes until it is restored. Its history is kept.${
            archiveTarget.quantity > 0 ? ` It still has ${archiveTarget.quantity} ${archiveTarget.unit} in stock.` : ""
          }`}
          confirmLabel="Archive"
          danger
          onConfirm={confirmArchive}
          onCancel={() => setArchiveTarget(null)}
        />
      )}
    </div>
  );
}
