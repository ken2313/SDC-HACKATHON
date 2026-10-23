import { useCallback, useEffect, useRef, useState } from "react";
import { activityLogsApi } from "../api/activityLogs.js";
import ApprovalBadge from "../components/ApprovalBadge.jsx";
import LogDetailModal from "../components/LogDetailModal.jsx";
import RolesPanel from "../components/RolesPanel.jsx";
import Spinner from "../components/Spinner.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { formatDateTime } from "../utils/stock.js";

const PERM_LOGS = "logs:view";
const PAGE_SIZE = 25;
const EMPTY_FILTERS = { search: "", category: "", approval: "", user_id: "", date_from: "", date_to: "" };

const CATEGORY_STYLES = {
  inventory: "bg-slate-100 text-slate-700",
  stock: "bg-sky-50 text-sky-700",
  alert: "bg-orange-50 text-orange-700",
  purchase_order: "bg-indigo-50 text-indigo-700",
  access: "bg-amber-50 text-amber-800",
  other: "bg-slate-100 text-slate-700",
};

function SummaryCard({ label, value, tone = "text-slate-900" }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value ?? "–"}</p>
    </div>
  );
}

const inputClass =
  "w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200";

// Employees reach this page only by typing the address. The backend answers 403 for them anyway.
function NoAccess() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4">
        <h1 className="text-lg font-semibold text-amber-900">Activity Logs are for the Owner / Admin</h1>
        <p className="mt-1 text-sm text-amber-800">
          Your role cannot read the audit log. Everything you do is still recorded in it, including blocked attempts.
        </p>
      </div>
      <RolesPanel />
    </div>
  );
}

export default function ActivityLogs() {
  const { can, business } = useSession();
  const allowed = can(PERM_LOGS);

  const [tab, setTab] = useState("log"); // "log" | "roles"
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [search, setSearch] = useState(""); // debounced copy of filters.search
  const [page, setPage] = useState(0);
  const [data, setData] = useState({ items: [], total: 0 });
  const [summary, setSummary] = useState(null);
  const [options, setOptions] = useState({ users: [], categories: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const latestRequest = useRef(0);

  // Wait until the user stops typing before asking the server
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(filters.search.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [filters.search]);

  const load = useCallback(async () => {
    if (!allowed) return;
    const requestNumber = ++latestRequest.current;
    setLoading(true);
    setError(null);
    try {
      const [list, counts] = await Promise.all([
        activityLogsApi.list({
          search,
          category: filters.category,
          approval: filters.approval,
          user_id: filters.user_id,
          date_from: filters.date_from,
          date_to: filters.date_to,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        }),
        activityLogsApi.summary(),
      ]);
      if (requestNumber !== latestRequest.current) return;
      setData(list);
      setSummary(counts);
    } catch (err) {
      if (requestNumber !== latestRequest.current) return;
      setError(err.message);
    } finally {
      if (requestNumber === latestRequest.current) setLoading(false);
    }
  }, [allowed, search, filters.category, filters.approval, filters.user_id, filters.date_from, filters.date_to, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!allowed) return;
    activityLogsApi.filters().then(setOptions).catch(() => {});
  }, [allowed]);

  if (!allowed) return <NoAccess />;

  function setFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
    if (name !== "search") setPage(0);
  }

  const hasFilters = Object.entries(filters).some(([, value]) => value !== "");
  const pageCount = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const from = data.total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = Math.min(data.total, (page + 1) * PAGE_SIZE);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Activity Logs</h1>
          <p className="text-sm text-slate-500">
            Who did what, when, and what changed in {business.name}. Entries are written automatically and cannot be edited.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <SummaryCard label="All entries" value={summary?.total} />
        <SummaryCard label="Last 24 hours" value={summary?.last_24_hours} />
        <SummaryCard label="Orders approved" value={summary?.approvals} tone="text-emerald-600" />
        <SummaryCard label="Orders rejected" value={summary?.rejections} tone="text-red-600" />
        <SummaryCard label="Blocked attempts" value={summary?.blocked_attempts} tone="text-amber-600" />
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {[
          ["log", "Log"],
          ["roles", "Roles and permissions"],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              tab === key ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "roles" ? (
        <RolesPanel />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-6">
            <div className="lg:col-span-2">
              <label htmlFor="log-search" className="mb-1 block text-xs font-medium text-slate-500">Search</label>
              <input
                id="log-search"
                type="search"
                value={filters.search}
                onChange={(event) => setFilter("search", event.target.value)}
                placeholder="Product, order number, text…"
                maxLength={100}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="log-category" className="mb-1 block text-xs font-medium text-slate-500">Type</label>
              <select id="log-category" value={filters.category} onChange={(e) => setFilter("category", e.target.value)} className={inputClass}>
                <option value="">All types</option>
                {options.categories.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="log-approval" className="mb-1 block text-xs font-medium text-slate-500">Approval</label>
              <select id="log-approval" value={filters.approval} onChange={(e) => setFilter("approval", e.target.value)} className={inputClass}>
                <option value="">Any</option>
                <option value="decisions">All decisions</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="denied">Blocked</option>
              </select>
            </div>
            <div>
              <label htmlFor="log-user" className="mb-1 block text-xs font-medium text-slate-500">User</label>
              <select id="log-user" value={filters.user_id} onChange={(e) => setFilter("user_id", e.target.value)} className={inputClass}>
                <option value="">Everyone</option>
                {options.users.map((u) => (
                  <option key={u.id} value={u.id}>{u.name}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-2">
              <div className="min-w-0 flex-1">
                <label htmlFor="log-from" className="mb-1 block text-xs font-medium text-slate-500">From</label>
                <input id="log-from" type="date" value={filters.date_from} max={filters.date_to || undefined} onChange={(e) => setFilter("date_from", e.target.value)} className={inputClass} />
              </div>
              <div className="min-w-0 flex-1">
                <label htmlFor="log-to" className="mb-1 block text-xs font-medium text-slate-500">To</label>
                <input id="log-to" type="date" value={filters.date_to} min={filters.date_from || undefined} onChange={(e) => setFilter("date_to", e.target.value)} className={inputClass} />
              </div>
            </div>
            {hasFilters && (
              <div className="sm:col-span-2 lg:col-span-6">
                <button
                  type="button"
                  onClick={() => {
                    setFilters(EMPTY_FILTERS);
                    setPage(0);
                  }}
                  className="text-sm font-medium text-indigo-600 hover:text-indigo-800"
                >
                  Clear filters
                </button>
              </div>
            )}
          </div>

          {error && (
            <div role="alert" className="flex items-center justify-between gap-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
              <span>{error}</span>
              <button type="button" onClick={load} className="font-medium underline">Try again</button>
            </div>
          )}

          <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
            {loading && data.items.length === 0 ? (
              <Spinner label="Loading activity…" className="py-16" />
            ) : data.items.length === 0 && !error ? (
              <p className="px-4 py-12 text-center text-sm text-slate-500">
                {hasFilters ? "No entries match these filters." : "Nothing has been recorded yet."}
              </p>
            ) : (
              <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}>
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">When</th>
                      <th className="px-4 py-2.5 font-medium">User</th>
                      <th className="px-4 py-2.5 font-medium">Action</th>
                      <th className="px-4 py-2.5 font-medium">Affected</th>
                      <th className="px-4 py-2.5 font-medium">Approval</th>
                      <th className="px-4 py-2.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((entry) => (
                      <tr key={entry.id} className="border-t border-slate-100 align-top hover:bg-slate-50/60">
                        <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDateTime(entry.created_at)}</td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <span className="text-slate-900">{entry.user_name}</span>
                          {entry.user_role && <span className="ml-1 text-xs text-slate-500">{entry.user_role}</span>}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${CATEGORY_STYLES[entry.category]}`}>
                            {entry.action_label}
                          </span>
                          <p className="mt-1 max-w-md text-slate-600">{entry.summary}</p>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-slate-700">{entry.entity_label ?? "–"}</td>
                        <td className="px-4 py-3"><ApprovalBadge status={entry.approval_status} /></td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => setSelected(entry)}
                            className="rounded-md px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                          >
                            Details
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {data.total > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
                <span>Showing {from}–{to} of {data.total}</span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0 || loading}
                    className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <span>Page {page + 1} of {pageCount}</span>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                    disabled={page + 1 >= pageCount || loading}
                    className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {selected && <LogDetailModal entry={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
