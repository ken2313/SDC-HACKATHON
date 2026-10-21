// Label + input wrapper with an inline error message.
export default function FormField({ label, htmlFor, error, hint, children }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

export function inputClass(hasError) {
  return `w-full rounded-lg border px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 ${
    hasError
      ? "border-red-400 focus:border-red-500 focus:ring-red-200"
      : "border-slate-300 focus:border-indigo-500 focus:ring-indigo-200"
  } disabled:bg-slate-100 disabled:text-slate-500`;
}
