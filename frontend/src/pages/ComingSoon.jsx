import { Link } from "react-router-dom";

// Honest placeholder for pages that belong to later features.
export default function ComingSoon({ title, feature, description }) {
  return (
    <div className="mx-auto max-w-xl py-16 text-center">
      <span className="inline-block rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-indigo-700">
        {feature ? `Planned for Feature ${feature}` : "Planned"}
      </span>
      <h1 className="mt-4 text-2xl font-semibold text-slate-900">{title}</h1>
      <p className="mt-3 text-sm leading-relaxed text-slate-600">{description}</p>
      <p className="mt-2 text-sm text-slate-500">This page is not built yet. We are developing one feature at a time.</p>
      <Link
        to="/inventory"
        className="mt-6 inline-block rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
      >
        Go to Inventory
      </Link>
    </div>
  );
}
