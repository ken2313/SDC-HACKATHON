import { useEffect, useState } from "react";
import { accessApi } from "../api/activityLogs.js";
import Spinner from "./Spinner.jsx";

// Shows the role rules the BACKEND enforces. (Simulated roles: no passwords.)
export default function RolesPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    accessApi
      .matrix()
      .then((result) => !cancelled && setData(result))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>;
  if (!data) return <Spinner label="Loading roles…" />;

  const areas = [...new Set(data.permissions.map((row) => row.area))];

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Roles and permissions</h2>
        <p className="text-xs text-slate-500">
          {data.note} You are signed in as <strong>{data.roles.find((r) => r.role === data.your_role)?.label}</strong>.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Action</th>
              {data.roles.map((role) => (
                <th
                  key={role.role}
                  className={`px-4 py-2 text-center font-medium ${role.role === data.your_role ? "text-indigo-700" : ""}`}
                >
                  {role.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {areas.map((area) => (
              <FragmentRows key={area} area={area} rows={data.permissions.filter((row) => row.area === area)} roles={data.roles} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FragmentRows({ area, rows, roles }) {
  return (
    <>
      <tr className="bg-slate-50/60">
        <td colSpan={roles.length + 1} className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          {area}
        </td>
      </tr>
      {rows.map((row) => (
        <tr key={row.key} className="border-t border-slate-100">
          <td className="px-4 py-2 text-slate-700">{row.description}</td>
          {roles.map((role) => (
            <td key={role.role} className="px-4 py-2 text-center">
              {row.allowed[role.role] ? (
                <span className="font-semibold text-emerald-600" aria-label="Allowed">✓</span>
              ) : (
                <span className="text-slate-300" aria-label="Not allowed">✕</span>
              )}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
