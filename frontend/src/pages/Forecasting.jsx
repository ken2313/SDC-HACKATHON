import { useCallback, useEffect, useRef, useState } from "react";
import { forecastsApi } from "../api/forecasts.js";
import ForecastDetailModal from "../components/ForecastDetailModal.jsx";
import ForecastStatusBadge from "../components/ForecastStatusBadge.jsx";
import Spinner from "../components/Spinner.jsx";
import ThresholdModal from "../components/ThresholdModal.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { formatDateOnly } from "../utils/money.js";

const PERM_MANAGE = "inventory:manage"; // changing a reorder level (owner)

const FILTERS = [
  ["action", "Needs action"],
  ["all", "All products"],
  ["insufficient_data", "Not enough data"],
];

function daysFrom(today, isoDate) {
  const [y1, m1, d1] = today.split("-").map(Number);
  const [y2, m2, d2] = isoDate.split("-").map(Number);
  return Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / 86400000);
}

function relative(today, isoDate) {
  if (!isoDate) return "";
  const days = daysFrom(today, isoDate);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  return days > 0 ? `in ${days} days` : `${-days} days ago`;
}

function SummaryCard({ label, value, tone = "text-slate-900", hint }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" title={hint}>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value ?? "–"}</p>
    </div>
  );
}

function MethodPanel({ method }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span>
          <span className="text-sm font-semibold text-slate-900">How the forecast works</span>
          <span className="ml-2 text-xs text-slate-500">{method.name}, checked against real use</span>
        </span>
        <span className="text-sm text-indigo-600">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
          <p>
            <strong className="text-slate-900">Demand</strong> is the number of units used each day (every stock removal), counted per
            Malaysian calendar day. Today is left out because it is not over yet.
          </p>
          <p>
            <strong className="text-slate-900">Forecast:</strong> the average daily use over the last {method.window_days} complete
            days. It is the same number for every future day: simple, explainable, and quick to react to change.
          </p>
          <p>
            <strong className="text-slate-900">Runs out</strong> = stock ÷ daily demand. <strong className="text-slate-900">Order by</strong>{" "}
            = the day stock falls to the demand during the supplier's delivery time plus {method.safety_days} safety days.{" "}
            <strong className="text-slate-900">Order quantity</strong> covers delivery time + {method.cover_days} days + {method.safety_days}{" "}
            safety days, minus stock on hand and stock already on order, and never less than the supplier's minimum.
          </p>
          <p>
            <strong className="text-slate-900">Accuracy:</strong> for each of the last {method.backtest_days} days we pretend it is that
            morning, forecast from the {method.window_days} days before it, and compare with what was really used. Accuracy = 100% minus
            total error ÷ total use. Below {method.low_accuracy_pct}% the dates are marked uncertain.
          </p>
          <p>
            <strong className="text-slate-900">Not enough data:</strong> fewer than {method.min_history_days} days of records means no
            forecast; fewer than {method.reliable_history_days} days gives a warning.
          </p>
          <p className="text-xs text-slate-500">
            Limits: no trends, holidays or promotions; a mistaken stock removal counts as demand (Feature 9 will flag unusual ones).
            Purchase order drafts still use the fixed rule from Purchase Orders; this page is advice for the owner.
          </p>
        </div>
      )}
    </section>
  );
}

export default function Forecasting() {
  const { can, business } = useSession();
  const toast = useToast();
  const canManage = can(PERM_MANAGE);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("action");
  const [openId, setOpenId] = useState(null);
  const [levelTarget, setLevelTarget] = useState(null);
  const latest = useRef(0);

  const load = useCallback(async () => {
    const requestNumber = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const result = await forecastsApi.list();
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

  function handleLevelSaved(newThreshold) {
    const name = levelTarget.item_name;
    setLevelTarget(null);
    setOpenId(null);
    toast.success(`Reorder level for ${name} is now ${newThreshold}.`);
    load();
  }

  if (!data) {
    return error ? (
      <div role="alert" className="mx-auto flex max-w-xl items-center justify-between gap-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
        <span>{error}</span>
        <button type="button" onClick={load} className="font-medium underline">Try again</button>
      </div>
    ) : (
      <Spinner label="Calculating forecasts…" />
    );
  }

  const { summary, today } = data;
  const rows = data.items.filter((row) => {
    if (filter === "action") return row.status === "order_now" || row.status === "order_soon" || row.level_check === "too_low";
    if (filter === "insufficient_data") return row.status === "insufficient_data";
    return true;
  });

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Demand Forecasting</h1>
          <p className="text-sm text-slate-500">
            When will each product run out, and when should {business.name} order? Based on the stock history.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
        >
          {loading ? "Recalculating…" : "Recalculate"}
        </button>
      </div>

      {error && <div role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">Could not refresh: {error}</div>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <SummaryCard label="Order now" value={summary.order_now} tone={summary.order_now ? "text-red-600" : "text-slate-900"} hint="Order-by date reached, nothing on order" />
        <SummaryCard label="Order this week" value={summary.order_soon} tone={summary.order_soon ? "text-amber-600" : "text-slate-900"} />
        <SummaryCard label="Runs out in 7 days" value={summary.run_out_within_7_days} hint="If nothing new is delivered" />
        <SummaryCard label="Reorder level too low" value={summary.reorder_level_too_low} tone={summary.reorder_level_too_low ? "text-amber-600" : "text-slate-900"} hint="Below the demand during delivery + safety days" />
        <SummaryCard
          label="Average accuracy"
          value={summary.average_accuracy_pct === null ? "–" : `${summary.average_accuracy_pct}%`}
          hint={`Predicted vs actual over the last ${data.method.backtest_days} days`}
        />
        <SummaryCard label="Not enough data" value={summary.insufficient_data} hint={`Fewer than ${data.method.min_history_days} days of records`} />
      </div>

      <MethodPanel method={data.method} />

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {FILTERS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              filter === key ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <p className="font-medium text-slate-900">
            {filter === "action" ? "Nothing needs ordering this week" : filter === "insufficient_data" ? "Every product has enough history" : "No products yet"}
          </p>
          <p className="mt-1 text-sm text-slate-500">Open “All products” to see every forecast.</p>
        </div>
      ) : (
        <div className={`overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm ${loading ? "opacity-60" : ""}`}>
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Product</th>
                <th className="px-4 py-3 font-medium">Advice</th>
                <th className="px-4 py-3 text-right font-medium">Demand / day</th>
                <th className="hidden px-4 py-3 text-right font-medium sm:table-cell">Stock</th>
                <th className="px-4 py-3 font-medium">Runs out</th>
                <th className="px-4 py-3 font-medium">Order by</th>
                <th className="hidden px-4 py-3 text-right font-medium md:table-cell">Order qty</th>
                <th className="hidden px-4 py-3 text-right font-medium lg:table-cell">Reorder level</th>
                <th className="hidden px-4 py-3 text-right font-medium lg:table-cell">Accuracy</th>
                <th className="px-4 py-3"><span className="sr-only">Details</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const late = row.order_by_date && daysFrom(today, row.order_by_date) < 0;
                return (
                  <tr key={row.item_id} className="border-t border-slate-100 align-top">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{row.item_name}</p>
                      <p className="text-xs text-slate-500">{row.sku} · {row.history_days} days of history</p>
                    </td>
                    <td className="px-4 py-3"><ForecastStatusBadge status={row.status} /></td>
                    <td className="whitespace-nowrap px-4 py-3 text-right text-slate-900">
                      {row.daily_forecast === null ? "–" : `${row.daily_forecast}`}
                      <span className="block text-xs text-slate-500">{row.unit}</span>
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-right text-slate-700 sm:table-cell">
                      {row.current_quantity}
                      {row.on_order > 0 && <span className="block text-xs text-sky-700">+{row.on_order} on order</span>}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                      {row.run_out_date ? (
                        <>
                          {formatDateOnly(row.run_out_date)}
                          <span className="block text-xs text-slate-500">{relative(today, row.run_out_date)}</span>
                        </>
                      ) : "–"}
                    </td>
                    <td className={`whitespace-nowrap px-4 py-3 ${late ? "font-medium text-red-600" : "text-slate-700"}`}>
                      {row.order_by_date ? (
                        <>
                          {late ? "Now" : formatDateOnly(row.order_by_date)}
                          <span className={`block text-xs ${late ? "text-red-600" : "text-slate-500"}`}>
                            {late ? `should have been ${relative(today, row.order_by_date)}` : relative(today, row.order_by_date)}
                          </span>
                        </>
                      ) : "–"}
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-right text-slate-900 md:table-cell">
                      {row.recommended_quantity === null ? "–" : row.recommended_quantity}
                      {row.recommended_quantity !== null && (
                        <span className="block text-xs text-slate-500">rule: {row.rule_quantity}</span>
                      )}
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-right lg:table-cell">
                      <span className="text-slate-900">{row.reorder_threshold}</span>
                      {row.suggested_reorder_level !== null && row.suggested_reorder_level !== row.reorder_threshold && (
                        <span className={`block text-xs ${row.level_check === "too_low" ? "font-medium text-amber-700" : "text-slate-500"}`}>
                          suggested {row.suggested_reorder_level}
                        </span>
                      )}
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-right lg:table-cell">
                      {row.accuracy_pct === null ? (
                        <span className="text-slate-400">–</span>
                      ) : (
                        <span className={row.accuracy_pct < data.method.low_accuracy_pct ? "text-amber-700" : "text-slate-700"}>
                          {row.accuracy_pct}%
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setOpenId(row.item_id)}
                        className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {openId !== null && !levelTarget && (
        <ForecastDetailModal itemId={openId} canManage={canManage} onClose={() => setOpenId(null)} onChangeLevel={setLevelTarget} />
      )}
      {levelTarget && (
        <ThresholdModal
          item={{
            item_id: levelTarget.item_id,
            item_name: levelTarget.item_name,
            sku: levelTarget.sku,
            unit: levelTarget.unit,
            quantity: levelTarget.current_quantity,
            reorder_threshold: levelTarget.reorder_threshold,
          }}
          initialValue={levelTarget.suggested_reorder_level}
          onClose={() => setLevelTarget(null)}
          onSaved={handleLevelSaved}
        />
      )}
    </div>
  );
}
