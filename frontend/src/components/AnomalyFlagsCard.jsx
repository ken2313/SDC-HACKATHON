// Feature 9: AI anomaly alerts on the dashboard.
// The backend asks the AI (PyTorch autoencoder on a RunPod GPU) after each stock OUT.
// A flag is a POTENTIAL anomaly for a person to review. It never changes stock.
import { useCallback, useEffect, useRef, useState } from "react";
import { getAiStatus, listAnomalies, reviewAnomaly } from "../api/anomalies.js";
import Spinner from "./Spinner.jsx";
import { formatDateTime } from "../utils/stock.js";

const STATUS_STYLES = {
  "Highly Unusual": "bg-red-50 text-red-700 ring-red-200",
  Unusual: "bg-amber-50 text-amber-800 ring-amber-200",
};
const REFRESH_MS = 15000; // the AI check runs in the background, so look again every 15 s

function oneDecimal(value) {
  return value === null || value === undefined ? "–" : Math.round(value * 10) / 10;
}

function FlagRow({ flag, onReviewed }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    if (!note.trim()) {
      setError("Please write a short note about what you found.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await reviewAnomaly(flag.id, note.trim());
      setOpen(false);
      setNote("");
      onReviewed();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-slate-900">{flag.product_name}</p>
          <p className="text-xs text-slate-500">{formatDateTime(flag.created_at)}</p>
        </div>
        <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${STATUS_STYLES[flag.status] ?? "bg-slate-50 text-slate-700 ring-slate-200"}`}>
          {flag.status}
        </span>
      </div>

      <p className="mt-1.5 text-sm text-slate-700">
        Used <span className="font-semibold">{flag.day_total_out} {flag.unit}</span> today · usually about{" "}
        <span className="font-semibold">{oneDecimal(flag.recent_avg_usage)}</span>
        {flag.expected_low !== null && flag.expected_high !== null && (
          <span className="text-slate-500"> (normal range {oneDecimal(flag.expected_low)}–{oneDecimal(flag.expected_high)})</span>
        )}
      </p>
      {flag.top_feature && <p className="mt-0.5 text-xs text-slate-600">Main reason: {flag.top_feature}</p>}
      <p className="mt-0.5 text-xs text-slate-400">
        Score {oneDecimal(flag.anomaly_score)}
        {flag.device === "cuda" ? " · checked on GPU" : flag.device ? ` · checked on ${flag.device}` : ""}
        {` · ${flag.history_days} days of history`}
      </p>
      <p className="mt-1 text-xs italic text-slate-500">{flag.note}</p>

      {flag.reviewed ? (
        <p className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          Reviewed by {flag.reviewed_by_name ?? "a team member"}
          {flag.reviewed_at ? ` on ${formatDateTime(flag.reviewed_at)}` : ""}: {flag.review_note}
        </p>
      ) : open ? (
        <form onSubmit={submit} className="mt-2 space-y-2">
          <label htmlFor={`review-note-${flag.id}`} className="block text-xs font-medium text-slate-700">
            What did you find?
          </label>
          <textarea
            id={`review-note-${flag.id}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
            rows={2}
            placeholder="e.g. Catering order, usage was real / Typo, should have been 4"
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
          {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save review"}
            </button>
            <button
              type="button"
              onClick={() => { setOpen(false); setError(null); }}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-2 rounded-lg border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
        >
          Review
        </button>
      )}
    </li>
  );
}

export default function AnomalyFlagsCard({ className = "" }) {
  const [view, setView] = useState("open");
  const [flags, setFlags] = useState(null);
  const [aiConfigured, setAiConfigured] = useState(true);
  const [error, setError] = useState(null);
  const latest = useRef(0);

  const load = useCallback(async () => {
    const requestNumber = ++latest.current;
    try {
      const [list, status] = await Promise.all([listAnomalies({ state: view }), getAiStatus()]);
      if (requestNumber === latest.current) {
        setFlags(list);
        setAiConfigured(Boolean(status?.ai_configured));
        setError(null);
      }
    } catch (err) {
      if (requestNumber === latest.current) setError(err.message);
    }
  }, [view]);

  useEffect(() => {
    setFlags(null);
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const toggle = (
    <div className="flex rounded-lg border border-slate-300 p-0.5" role="group" aria-label="Show">
      {[["open", "To review"], ["reviewed", "Reviewed"]].map(([value, label]) => (
        <button
          key={value}
          type="button"
          onClick={() => setView(value)}
          aria-pressed={view === value}
          className={`rounded-md px-2 py-1 text-xs font-medium ${view === value ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );

  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">AI anomaly alerts</h2>
          <p className="mt-0.5 text-xs text-slate-500">Unusual stock usage flagged by the AI for a person to check</p>
        </div>
        {toggle}
      </div>
      <div className="p-4">
        {!aiConfigured && (
          <p className="mb-3 rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-600">
            AI unavailable: the anomaly service is not connected right now. Stock updates still work normally.
          </p>
        )}
        {error ? (
          <div role="alert" className="flex items-center justify-between gap-3 text-sm text-red-600">
            <span>{error}</span>
            <button type="button" onClick={load} className="font-medium underline">Try again</button>
          </div>
        ) : flags === null ? (
          <Spinner label="Loading AI alerts…" />
        ) : flags.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">
            {view === "open" ? "Nothing unusual to review." : "No reviewed alerts yet."}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {flags.map((flag) => (
              <FlagRow key={flag.id} flag={flag} onReviewed={load} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}