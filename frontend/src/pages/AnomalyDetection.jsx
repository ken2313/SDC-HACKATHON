// Feature 9: AI Anomaly Detection page.
// Every stock OUT is checked in the background by a PyTorch autoencoder on a RunPod GPU.
// Flags are POTENTIAL anomalies for a person to review. The AI never changes stock.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { listAnomalies } from "../api/anomalies.js";
import AnomalyFlagsCard from "../components/AnomalyFlagsCard.jsx";
import Spinner from "../components/Spinner.jsx";
import { formatDateTime } from "../utils/stock.js";

const STEPS = [
  ["1. Stock removed", "An employee records a stock OUT on the Inventory page. The stock updates straight away."],
  ["2. Usage compared", "In the background, the backend adds up today's usage and compares it with the last 30 days."],
  ["3. AI checks it", "A small PyTorch autoencoder on a RunPod GPU scores how unusual it is."],
  ["4. A person decides", "Unusual results are flagged here. Someone reviews them, and the review is logged."],
];

const RESULT_STYLES = {
  Normal: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  Unusual: "bg-amber-50 text-amber-800 ring-amber-200",
  "Highly Unusual": "bg-red-50 text-red-700 ring-red-200",
};
const REFRESH_MS = 15000;

function oneDecimal(value) {
  return value === null || value === undefined ? "–" : Math.round(value * 10) / 10;
}

function AllChecks() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const latest = useRef(0);

  const load = useCallback(async () => {
    const requestNumber = ++latest.current;
    try {
      const data = await listAnomalies({ state: "all", results: "all" });
      if (requestNumber === latest.current) {
        setRows(data);
        setError(null);
      }
    } catch (err) {
      if (requestNumber === latest.current) setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">All AI checks</h2>
          <p className="mt-0.5 text-xs text-slate-500">Every stock OUT the AI has checked, including normal ones (latest 100)</p>
        </div>
        <button type="button" onClick={load} className="text-xs font-medium text-indigo-600 hover:text-indigo-800">
          Refresh
        </button>
      </div>
      <div className="p-4">
        {error ? (
          <div role="alert" className="flex items-center justify-between gap-3 text-sm text-red-600">
            <span>{error}</span>
            <button type="button" onClick={load} className="font-medium underline">Try again</button>
          </div>
        ) : rows === null ? (
          <Spinner label="Loading AI checks…" />
        ) : rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">
            No AI checks yet. Record a stock removal on the{" "}
            <Link to="/inventory" className="font-medium text-indigo-600 hover:text-indigo-800">Inventory</Link> page.
          </p>
        ) : (
          <div className="-mx-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2 font-medium">When</th>
                  <th className="px-4 py-2 font-medium">Product</th>
                  <th className="px-4 py-2 text-right font-medium">Used today</th>
                  <th className="hidden px-4 py-2 font-medium md:table-cell">Usual</th>
                  <th className="px-4 py-2 font-medium">Result</th>
                  <th className="hidden px-4 py-2 text-right font-medium sm:table-cell">Score</th>
                  <th className="hidden px-4 py-2 font-medium lg:table-cell">Ran on</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-t border-slate-100 align-top">
                    <td className="whitespace-nowrap px-4 py-2 text-slate-600">{formatDateTime(row.created_at)}</td>
                    <td className="px-4 py-2">
                      <p className="font-medium text-slate-900">{row.product_name}</p>
                      {row.reviewed && <p className="text-xs text-emerald-700">Reviewed by {row.reviewed_by_name ?? "a team member"}</p>}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-right text-slate-700">{row.day_total_out} {row.unit}</td>
                    <td className="hidden whitespace-nowrap px-4 py-2 text-slate-600 md:table-cell">
                      ~{oneDecimal(row.recent_avg_usage)}
                      {row.expected_low !== null && row.expected_high !== null && (
                        <span className="text-xs text-slate-500"> ({oneDecimal(row.expected_low)}–{oneDecimal(row.expected_high)})</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${RESULT_STYLES[row.status] ?? "bg-slate-50 text-slate-700 ring-slate-200"}`}>
                        {row.status}
                      </span>
                      {row.reason && <p className="mt-1 text-xs text-slate-500">{row.reason}</p>}
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-2 text-right text-slate-600 sm:table-cell">{oneDecimal(row.anomaly_score)}</td>
                    <td className="hidden whitespace-nowrap px-4 py-2 text-slate-600 lg:table-cell">
                      {row.device === "cuda" ? "GPU (CUDA)" : row.device ?? "–"}
                      {row.inference_ms !== null && <span className="block text-xs text-slate-500">{oneDecimal(row.inference_ms)} ms</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export default function AnomalyDetection() {
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">AI Anomaly Detection</h1>
        <p className="text-sm text-slate-500">
          A PyTorch autoencoder on a RunPod GPU checks every stock removal against the product's recent daily usage.
          Flags are for human review and never change stock.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map(([title, text]) => (
          <div key={title} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-sm font-semibold text-slate-900">{title}</p>
            <p className="mt-1 text-xs text-slate-600">{text}</p>
          </div>
        ))}
      </div>

      <AnomalyFlagsCard />

      <AllChecks />

      <p className="text-xs text-slate-500">
        Synthetic data only. The model learned "normal" usage from synthetic café data. In testing, a simple
        statistical baseline performed about as well on these simple spikes, so the AI is a second pair of eyes,
        not the final word.
      </p>
    </div>
  );
}