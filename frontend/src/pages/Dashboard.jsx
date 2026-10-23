import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { dashboardApi } from "../api/dashboard.js";
import OrderStatusBadge from "../components/OrderStatusBadge.jsx";
import Spinner from "../components/Spinner.jsx";
import UrgencyBadge from "../components/UrgencyBadge.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { formatDateOnly, formatRM } from "../utils/money.js";
import { formatDateTime } from "../utils/stock.js";

// Chart colours (Tailwind palette values, so the charts match the rest of the app)
const COLORS = {
  line: "#4f46e5", // indigo-600: stock on hand
  used: "#94a3b8", // slate-400: units used
  added: "#10b981", // emerald-500: units added
  threshold: "#d97706", // amber-600: reorder level
  inStock: "#10b981",
  lowStock: "#f59e0b",
  outOfStock: "#ef4444",
  grid: "#e2e8f0",
  axis: "#64748b",
};

const RANGES = [14, 30, 60];

function shortDate(isoDate) {
  const [year, month, day] = String(isoDate).split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-MY", { day: "numeric", month: "short" });
}

function StatCard({ label, value, hint, tone = "text-slate-900", to }) {
  const body = (
    <>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value ?? "–"}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </>
  );
  const style = "block rounded-xl border border-slate-200 bg-white p-4 shadow-sm";
  return to ? (
    <Link to={to} className={`${style} transition hover:border-indigo-300 hover:shadow`}>
      {body}
    </Link>
  ) : (
    <div className={style}>{body}</div>
  );
}

function Panel({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function EmptyNote({ children }) {
  return <p className="py-6 text-center text-sm text-slate-500">{children}</p>;
}

// ---------------------------------------------------------------- stock trend (one product)

function TrendTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <p className="font-medium text-slate-900">{formatDateOnly(label)}</p>
      <p className="text-slate-700">On hand: {point.quantity ?? "–"} {unit}</p>
      <p className="text-slate-500">Used: {point.stock_out} · Added: {point.stock_in}</p>
    </div>
  );
}

function StockTrendPanel({ products, defaultItemId }) {
  const [itemId, setItemId] = useState(defaultItemId);
  const [days, setDays] = useState(30);
  const [trend, setTrend] = useState(null);
  const [error, setError] = useState(null);
  const latest = useRef(0);

  useEffect(() => {
    setItemId(defaultItemId);
  }, [defaultItemId]);

  useEffect(() => {
    if (!itemId) return;
    const requestNumber = ++latest.current;
    setError(null);
    dashboardApi
      .trend(itemId, days)
      .then((data) => {
        if (requestNumber === latest.current) setTrend(data);
      })
      .catch((err) => {
        if (requestNumber === latest.current) setError(err.message);
      });
  }, [itemId, days]);

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor="trend-product" className="sr-only">Product</label>
      <select
        id="trend-product"
        value={itemId ?? ""}
        onChange={(e) => setItemId(Number(e.target.value))}
        className="max-w-[14rem] rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
      >
        {products.map((p) => (
          <option key={p.item_id} value={p.item_id}>{p.item_name}</option>
        ))}
      </select>
      <div className="flex rounded-lg border border-slate-300 p-0.5" role="group" aria-label="Period">
        {RANGES.map((range) => (
          <button
            key={range}
            type="button"
            onClick={() => setDays(range)}
            aria-pressed={days === range}
            className={`rounded-md px-2 py-1 text-xs font-medium ${days === range ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}
          >
            {range}d
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <Panel
      title="Stock trend"
      subtitle="Stock at the end of each day, with units used and added. Rebuilt from the stock movements."
      action={products.length > 0 ? controls : null}
      className="lg:col-span-2"
    >
      {products.length === 0 ? (
        <EmptyNote>Add a product to see its trend.</EmptyNote>
      ) : error ? (
        <p role="alert" className="text-sm text-red-600">{error}</p>
      ) : !trend ? (
        <Spinner label="Loading trend…" />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <span className="text-slate-600">
              Now <span className="font-semibold text-slate-900">{trend.current_quantity} {trend.unit}</span>
            </span>
            <span className="text-slate-600">
              Reorder at <span className="font-semibold text-slate-900">{trend.reorder_threshold}</span>
            </span>
            <span className="text-slate-600">
              Average use <span className="font-semibold text-slate-900">{trend.average_daily_usage} / day</span>
            </span>
            <span className="text-slate-600">
              {days} days: used <span className="font-semibold text-slate-900">{trend.total_out}</span>, added{" "}
              <span className="font-semibold text-slate-900">{trend.total_in}</span>
            </span>
          </div>
          {!trend.enough_history && (
            <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Not much history yet for this product ({trend.days_with_usage} day{trend.days_with_usage === 1 ? "" : "s"} with usage in this period), so the trend says little so far.
            </p>
          )}
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={trend.points} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid stroke={COLORS.grid} vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: COLORS.axis }} minTickGap={16} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: COLORS.axis }} />
                <Tooltip content={<TrendTooltip unit={trend.unit} />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="stock_out" name="Used" fill={COLORS.used} radius={[3, 3, 0, 0]} maxBarSize={14} />
                <Bar dataKey="stock_in" name="Added" fill={COLORS.added} radius={[3, 3, 0, 0]} maxBarSize={14} />
                <Line type="stepAfter" dataKey="quantity" name="On hand" stroke={COLORS.line} strokeWidth={2} dot={false} connectNulls={false} />
                <ReferenceLine
                  y={trend.reorder_threshold}
                  stroke={COLORS.threshold}
                  strokeDasharray="5 4"
                  label={{ value: "Reorder level", position: "insideTopRight", fontSize: 11, fill: COLORS.threshold }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- stock status per category

function CategoryPanel({ rows }) {
  const height = Math.max(160, rows.length * 34 + 60);
  return (
    <Panel title="Stock status by category" subtitle="Number of products in each status (archived products not counted)">
      {rows.length === 0 ? (
        <EmptyNote>No products yet.</EmptyNote>
      ) : (
        <div className="w-full" style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
              <CartesianGrid stroke={COLORS.grid} horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: COLORS.axis }} />
              <YAxis type="category" dataKey="category" width={96} tick={{ fontSize: 11, fill: COLORS.axis }} />
              <Tooltip cursor={{ fill: "#f1f5f9" }} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="in_stock" name="In stock" stackId="s" fill={COLORS.inStock} maxBarSize={18} />
              <Bar dataKey="low_stock" name="Low stock" stackId="s" fill={COLORS.lowStock} maxBarSize={18} />
              <Bar dataKey="out_of_stock" name="Out of stock" stackId="s" fill={COLORS.outOfStock} maxBarSize={18} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- lists

function UrgentPanel({ rows, openAlerts }) {
  return (
    <Panel
      title="Urgent products"
      subtitle={`${openAlerts} open low-stock alert${openAlerts === 1 ? "" : "s"}, most urgent first`}
      action={<Link to="/stock-alerts" className="text-xs font-medium text-indigo-600 hover:text-indigo-800">All alerts</Link>}
    >
      {rows.length === 0 ? (
        <EmptyNote>Nothing is low. Every product is above its reorder level.</EmptyNote>
      ) : (
        <ul className="divide-y divide-slate-100">
          {rows.map((row) => (
            <li key={row.item_id} className="py-2.5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-slate-900">{row.item_name}</p>
                  <p className="text-xs text-slate-500">
                    {row.quantity} {row.unit} left · reorder at {row.reorder_threshold}
                  </p>
                </div>
                <UrgencyBadge urgency={row.urgency} />
              </div>
              <p className="mt-1 text-xs">
                {row.order_po_number ? (
                  <span className="text-slate-600">
                    On order: {row.order_po_number} ({row.order_status.replace("_", " ")})
                  </span>
                ) : (
                  <span className="font-medium text-amber-700">No order yet</span>
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function DeliveriesPanel({ rows }) {
  return (
    <Panel
      title="Upcoming deliveries"
      subtitle="Orders with the supplier, due in the next 14 days or overdue"
      action={<Link to="/supplier-orders" className="text-xs font-medium text-indigo-600 hover:text-indigo-800">Supplier Orders</Link>}
    >
      {rows.length === 0 ? (
        <EmptyNote>No deliveries expected. Placed orders appear here.</EmptyNote>
      ) : (
        <ul className="divide-y divide-slate-100">
          {rows.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div>
                <p className="text-sm font-medium text-slate-900">
                  {row.po_number} <span className="font-normal text-slate-500">· {row.supplier_name}</span>
                </p>
                <p className={`text-xs ${row.is_overdue ? "font-medium text-red-600" : "text-slate-500"}`}>
                  {row.is_overdue
                    ? `Overdue by ${-row.days_until} day${row.days_until === -1 ? "" : "s"} (expected ${formatDateOnly(row.estimated_delivery_date)})`
                    : row.days_until === 0
                      ? "Expected today"
                      : `Expected ${formatDateOnly(row.estimated_delivery_date)} (in ${row.days_until} day${row.days_until === 1 ? "" : "s"})`}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-slate-700">{formatRM(row.total)}</span>
                <OrderStatusBadge status={row.status} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

const MOVEMENT_LABELS = { initial: "Opening stock", in: "Added", out: "Removed" };

function ActivityPanel({ rows }) {
  return (
    <Panel
      title="Recent inventory activity"
      subtitle="The latest stock movements, newest first"
      action={<Link to="/inventory" className="text-xs font-medium text-indigo-600 hover:text-indigo-800">Inventory</Link>}
      className="lg:col-span-2"
    >
      {rows.length === 0 ? (
        <EmptyNote>No stock movements yet.</EmptyNote>
      ) : (
        <div className="-mx-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">When</th>
                <th className="px-4 py-2 font-medium">Product</th>
                <th className="px-4 py-2 text-right font-medium">Change</th>
                <th className="hidden px-4 py-2 font-medium sm:table-cell">Stock</th>
                <th className="hidden px-4 py-2 font-medium md:table-cell">By</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-slate-100 align-top">
                  <td className="whitespace-nowrap px-4 py-2 text-slate-600">{formatDateTime(row.created_at)}</td>
                  <td className="px-4 py-2">
                    <p className="font-medium text-slate-900">{row.item_name}</p>
                    {row.reason && <p className="text-xs text-slate-500">{row.reason}</p>}
                  </td>
                  <td className={`whitespace-nowrap px-4 py-2 text-right font-medium ${row.quantity_change < 0 ? "text-red-600" : "text-emerald-600"}`}>
                    {row.quantity_change > 0 ? "+" : ""}
                    {row.quantity_change} {row.unit}
                    <span className="block text-xs font-normal text-slate-500">{MOVEMENT_LABELS[row.movement_type] ?? row.movement_type}</span>
                  </td>
                  <td className="hidden whitespace-nowrap px-4 py-2 text-slate-600 sm:table-cell">
                    {row.quantity_before} → {row.quantity_after}
                  </td>
                  <td className="hidden px-4 py-2 text-slate-600 md:table-cell">{row.user_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function AnomalyPanel({ status }) {
  return (
    <Panel title="AI anomaly alerts" subtitle="Unusual stock movements flagged for human review">
      <div className="rounded-lg border border-dashed border-slate-300 px-4 py-6 text-center">
        <span className="inline-block rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-indigo-700">
          Planned for Feature 9
        </span>
        <p className="mt-3 text-sm text-slate-600">{status.message}</p>
        <p className="mt-1 text-xs text-slate-500">Nothing is shown here until real results from the RunPod model exist.</p>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- page

export default function Dashboard() {
  const { business } = useSession();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const latest = useRef(0);

  const load = useCallback(async () => {
    const requestNumber = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const result = await dashboardApi.overview();
      if (requestNumber === latest.current) setData(result);
    } catch (err) {
      if (requestNumber === latest.current) setError(err.message);
    } finally {
      if (requestNumber === latest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!data) {
    return error ? (
      <div role="alert" className="mx-auto flex max-w-xl items-center justify-between gap-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
        <span>{error}</span>
        <button type="button" onClick={load} className="font-medium underline">Try again</button>
      </div>
    ) : (
      <Spinner label="Loading dashboard…" />
    );
  }

  const { stock, alerts, orders, financials } = data;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500">
            {business.name} · {formatDateOnly(data.today)} · updated {formatDateTime(data.generated_at)}
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

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          Could not refresh: {error}. Showing the last numbers loaded.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Products" value={stock.total_products} hint={`${stock.in_stock} in stock`} to="/inventory" />
        <StatCard label="Low stock" value={stock.low_stock} tone={stock.low_stock ? "text-amber-600" : "text-slate-900"} hint="At or below reorder level" to="/stock-alerts" />
        <StatCard label="Out of stock" value={stock.out_of_stock} tone={stock.out_of_stock ? "text-red-600" : "text-slate-900"} hint={`${alerts.critical} critical alert${alerts.critical === 1 ? "" : "s"}`} to="/stock-alerts" />
        <StatCard label="Pending orders" value={orders.pending_approval} tone={orders.pending_approval ? "text-indigo-600" : "text-slate-900"} hint="Waiting for owner approval" to="/purchase-orders" />
        <StatCard
          label="Delayed orders"
          value={orders.delayed_or_overdue}
          tone={orders.delayed_or_overdue ? "text-red-600" : "text-slate-900"}
          hint={`${orders.delayed} delayed · ${orders.overdue} overdue`}
          to="/supplier-orders"
        />
        <StatCard label="Awaiting delivery" value={orders.awaiting_delivery} hint={`${orders.approved_not_placed} approved, not placed`} to="/supplier-orders" />
      </div>

      {financials ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Stock value"
            value={formatRM(financials.stock_value)}
            hint={financials.products_without_price ? `${financials.products_without_price} product(s) have no price` : "At current supplier prices"}
          />
          <StatCard label="Waiting for approval" value={formatRM(financials.pending_approval_value)} hint="Draft purchase orders" />
          <StatCard label="On order" value={formatRM(financials.on_order_value)} hint="Approved, not yet received" />
          <StatCard label="Received (30 days)" value={formatRM(financials.received_last_30_days)} hint="Confirmed deliveries" />
        </div>
      ) : (
        <p className="text-xs text-slate-500">Money totals are shown to the owner only.</p>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <StockTrendPanel products={data.trend_products} defaultItemId={data.default_trend_item_id} />
        <UrgentPanel rows={data.urgent_products} openAlerts={alerts.open} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <CategoryPanel rows={data.status_by_category} />
        <DeliveriesPanel rows={data.upcoming_deliveries} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <ActivityPanel rows={data.recent_activity} />
        <AnomalyPanel status={data.anomalies} />
      </div>
    </div>
  );
}
