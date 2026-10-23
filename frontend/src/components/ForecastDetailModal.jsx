import { useEffect, useRef, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { forecastsApi } from "../api/forecasts.js";
import { formatDateOnly } from "../utils/money.js";
import ForecastStatusBadge from "./ForecastStatusBadge.jsx";
import Modal from "./Modal.jsx";
import Spinner from "./Spinner.jsx";

const COLORS = {
  actual: "#94a3b8",     // slate-400
  predicted: "#4f46e5",  // indigo-600
  stock: "#0ea5e9",      // sky-500
  level: "#d97706",      // amber-600
  suggested: "#dc2626",  // red-600
  grid: "#e2e8f0",
  axis: "#64748b",
};
const HORIZONS = [7, 14, 30];

function shortDate(isoDate) {
  const [year, month, day] = String(isoDate).split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-MY", { day: "numeric", month: "short" });
}

function Fact({ label, value, hint }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2" title={hint}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}

// Shows the sums with this product's own numbers, so the result can be checked by hand.
function Working({ data }) {
  const { method, unit } = data;
  const lead = data.lead_time_days ?? 0;
  const d = data.daily_forecast;
  return (
    <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
      <li>
        Daily demand = units used over the last {method.window_days} complete days ÷ {method.window_days} ={" "}
        <strong className="text-slate-900">{d} {unit}/day</strong>.
      </li>
      <li>
        Runs out in {data.current_quantity} ÷ {d} = <strong className="text-slate-900">{data.days_until_out} days</strong>
        {data.run_out_date ? ` (${formatDateOnly(data.run_out_date)})` : ""}, if nothing new arrives.
      </li>
      <li>
        Order by: {data.days_until_out} − {lead} delivery day{lead === 1 ? "" : "s"} − {method.safety_days} safety days →{" "}
        <strong className="text-slate-900">{formatDateOnly(data.order_by_date)}</strong>
        {data.supplier_name ? ` (${data.supplier_name})` : " (no supplier price, 0 delivery days assumed)"}.
      </li>
      <li>
        Order {d} × ({lead} + {method.cover_days} + {method.safety_days} days) − {data.current_quantity} on hand
        {data.on_order ? ` − ${data.on_order} on order` : ""} ={" "}
        <strong className="text-slate-900">{data.recommended_quantity} {unit}</strong>
        {data.min_order_qty ? ` (supplier minimum ${data.min_order_qty})` : ""}.
      </li>
      <li>
        Suggested reorder level = {d} × ({lead} + {method.safety_days}) ={" "}
        <strong className="text-slate-900">{data.suggested_reorder_level}</strong> (now {data.reorder_threshold}).
      </li>
    </ol>
  );
}

export default function ForecastDetailModal({ itemId, canManage, onClose, onChangeLevel }) {
  const [horizon, setHorizon] = useState(14);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const latest = useRef(0);

  useEffect(() => {
    const requestNumber = ++latest.current;
    setError(null);
    forecastsApi
      .get(itemId, horizon)
      .then((result) => {
        if (requestNumber === latest.current) setData(result);
      })
      .catch((err) => {
        if (requestNumber === latest.current) setError(err.message);
      });
  }, [itemId, horizon]);

  const hasForecast = data && data.daily_forecast !== null;

  return (
    <Modal
      title={data ? data.item_name : "Forecast"}
      subtitle={data ? `${data.sku} · ${data.current_quantity} ${data.unit} on hand · reorder at ${data.reorder_threshold}` : undefined}
      onClose={onClose}
      size="lg"
    >
      {error ? (
        <p role="alert" className="text-sm text-red-600">{error}</p>
      ) : !data ? (
        <Spinner label="Loading forecast…" />
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <ForecastStatusBadge status={data.status} />
            {data.accuracy_pct !== null && (
              <span className="text-xs text-slate-500">
                Accuracy {data.accuracy_pct}% on the last {data.backtest_days} days (average error {data.mean_absolute_error} {data.unit}/day)
              </span>
            )}
          </div>

          {data.warnings.length > 0 && (
            <ul className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {data.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}

          {hasForecast && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Fact label="Demand / day" value={`${data.daily_forecast} ${data.unit}`} hint="7-day moving average" />
              <Fact label="Runs out" value={data.run_out_date ? formatDateOnly(data.run_out_date) : "Not expected"} />
              <Fact label="Order by" value={data.order_by_date ? formatDateOnly(data.order_by_date) : "–"} />
              <Fact
                label="Order quantity"
                value={`${data.recommended_quantity} ${data.unit}`}
                hint={`The fixed rule from Purchase Orders would order ${data.rule_quantity}`}
              />
            </div>
          )}

          <section>
            <h3 className="text-sm font-semibold text-slate-900">Predicted vs actual (last 28 days)</h3>
            <p className="text-xs text-slate-500">
              Bars: units really used each day. Line: what the 7-day average predicted that morning.
            </p>
            <div className="mt-2 h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={data.history} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke={COLORS.grid} vertical={false} />
                  <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: COLORS.axis }} minTickGap={16} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: COLORS.axis }} />
                  <Tooltip labelFormatter={formatDateOnly} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="actual" name="Actual use" fill={COLORS.actual} radius={[3, 3, 0, 0]} maxBarSize={14} />
                  <Line type="monotone" dataKey="predicted" name="Predicted" stroke={COLORS.predicted} strokeWidth={2} dot={false} connectNulls={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </section>

          {hasForecast && (
            <section>
              <div className="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">Projected stock (next {horizon} days)</h3>
                  <p className="text-xs text-slate-500">If nothing new is delivered. Dashed lines: current and suggested reorder levels.</p>
                </div>
                <div className="flex rounded-lg border border-slate-300 p-0.5" role="group" aria-label="Forecast period">
                  {HORIZONS.map((value) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setHorizon(value)}
                      aria-pressed={horizon === value}
                      className={`rounded-md px-2 py-1 text-xs font-medium ${horizon === value ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}
                    >
                      {value}d
                    </button>
                  ))}
                </div>
              </div>
              <div className="mt-2 h-52 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.future} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                    <CartesianGrid stroke={COLORS.grid} vertical={false} />
                    <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: COLORS.axis }} minTickGap={16} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: COLORS.axis }} />
                    <Tooltip labelFormatter={formatDateOnly} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="linear" dataKey="projected_stock" name={`Stock (${data.unit})`} stroke={COLORS.stock} strokeWidth={2} dot={false} />
                    <ReferenceLine y={data.reorder_threshold} stroke={COLORS.level} strokeDasharray="5 4"
                      label={{ value: "Reorder level", position: "insideTopRight", fontSize: 11, fill: COLORS.level }} />
                    {data.suggested_reorder_level !== data.reorder_threshold && (
                      <ReferenceLine y={data.suggested_reorder_level} stroke={COLORS.suggested} strokeDasharray="2 3"
                        label={{ value: "Suggested", position: "insideBottomRight", fontSize: 11, fill: COLORS.suggested }} />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          {hasForecast && data.daily_forecast > 0 && (
            <section>
              <h3 className="mb-1 text-sm font-semibold text-slate-900">How these numbers were worked out</h3>
              <Working data={data} />
            </section>
          )}

          {canManage && hasForecast && data.level_check === "too_low" && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
              <p className="text-sm text-indigo-900">
                Raise the reorder level from {data.reorder_threshold} to {data.suggested_reorder_level} so low-stock alerts and draft orders start in time?
              </p>
              <button
                type="button"
                onClick={() => onChangeLevel(data)}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Review new level
              </button>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
