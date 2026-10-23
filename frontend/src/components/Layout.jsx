import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../context/SessionContext.jsx";
import { NAV_ITEMS } from "../navigation.js";

function Sidebar({ onNavigate }) {
  const { can } = useSession();
  // Items that need a permission are hidden from roles without it. This is only tidiness:
  // the backend refuses the request anyway.
  const items = NAV_ITEMS.filter((item) => !item.permission || can(item.permission));
  return (
    <nav className="flex h-full flex-col bg-slate-900 text-slate-300">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500 text-sm font-bold text-white">SI</div>
        <div>
          <p className="text-sm font-semibold text-white">Smart Inventory</p>
          <p className="text-xs text-slate-400">Supplier Order Management</p>
        </div>
      </div>
      <ul className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
        {items.map((item) => (
          <li key={item.path}>
            <NavLink
              to={item.path}
              onClick={onNavigate}
              className={({ isActive }) =>
                `flex items-center justify-between rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? "bg-indigo-600 text-white" : "hover:bg-slate-800 hover:text-white"
                }`
              }
            >
              <span>{item.label}</span>
              {!item.live && (
                <span className="rounded bg-slate-700/70 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300">
                  {item.feature ? `F${item.feature}` : "Later"}
                </span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
      <p className="px-5 py-4 text-[11px] leading-snug text-slate-500">
        Demo build. All data is synthetic. Orbyte integration is simulated.
      </p>
    </nav>
  );
}

function SessionSwitcher() {
  const { users, user, business, switchUser } = useSession();

  // Group demo users by business for the dropdown
  const groups = users.reduce((acc, demoUser) => {
    (acc[demoUser.business_name] ??= []).push(demoUser);
    return acc;
  }, {});

  return (
    <div className="flex flex-col items-end gap-0.5">
      <label htmlFor="session-switcher" className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
        Simulated Orbyte session
      </label>
      <div className="flex items-center gap-2">
        <span
          className={`hidden rounded-full px-2 py-0.5 text-xs font-medium sm:inline ${
            user.role === "owner" ? "bg-indigo-50 text-indigo-700" : "bg-slate-100 text-slate-600"
          }`}
        >
          {user.role === "owner" ? "Owner" : "Employee"}
        </span>
        <select
          id="session-switcher"
          value={user.id}
          onChange={(event) => switchUser(Number(event.target.value))}
          className="max-w-[14rem] rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 sm:max-w-xs"
          title={`Business: ${business.name}`}
        >
          {Object.entries(groups).map(([businessName, members]) => (
            <optgroup key={businessName} label={businessName}>
              {members.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name} ({member.role})
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>
    </div>
  );
}

export default function Layout() {
  const { business } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen lg:flex">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 lg:block">
        <div className="fixed inset-y-0 w-64">
          <Sidebar />
        </div>
      </aside>

      {/* Mobile drawer */}
      {menuOpen && (
        <div className="fixed inset-0 z-30 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMenuOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64 shadow-xl">
            <Sidebar onNavigate={() => setMenuOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Open menu"
              className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm text-slate-600 lg:hidden"
            >
              ☰
            </button>
            <div>
              <p className="text-xs text-slate-500">Business</p>
              <p className="text-sm font-semibold text-slate-900">{business.name}</p>
            </div>
          </div>
          <SessionSwitcher />
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
