import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { settingsApi } from "../api/settings.js";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import { inputClass } from "../components/FormField.jsx";
import Spinner from "../components/Spinner.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useSession } from "../context/SessionContext.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { START_PAGES, getStartPage, setStartPage } from "../utils/preferences.js";
import { formatDateTime } from "../utils/stock.js";

function Section({ title, description, children }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
      </div>
      <div className="space-y-4 px-5 py-4">{children}</div>
    </section>
  );
}

function Row({ label, hint, children }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-medium text-slate-800">{label}</p>
        {hint && <p className="text-xs text-slate-500">{hint}</p>}
      </div>
      <div className="sm:max-w-sm sm:flex-1 sm:text-right">{children}</div>
    </div>
  );
}

function Toggle({ checked, onChange, disabled, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-indigo-600" : "bg-slate-300"
      }`}
    >
      <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${checked ? "translate-x-5" : "translate-x-0.5"}`} />
    </button>
  );
}

export default function Settings() {
  const { email, expiresAt, logout } = useAuth();
  const { user, business, switchUser } = useSession();
  const toast = useToast();

  const [settings, setSettings] = useState(null);
  const [error, setError] = useState(null);
  const [name, setName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [savingDrafts, setSavingDrafts] = useState(false);
  const [startPage, setStartPageState] = useState(getStartPage());
  const [confirmLogout, setConfirmLogout] = useState(false);

  useEffect(() => {
    settingsApi
      .get()
      .then((data) => {
        setSettings(data);
        setName(data.business_name);
      })
      .catch((err) => setError(err.message));
  }, []);

  async function save(payload, setBusy, successText) {
    setBusy(true);
    try {
      const updated = await settingsApi.update(payload);
      setSettings(updated);
      setName(updated.business_name);
      toast.success(successText(updated));
      if (payload.business_name) switchUser(user.id); // refresh the business name in the top bar
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  function saveName(event) {
    event.preventDefault();
    const clean = name.trim();
    if (clean.length < 2) {
      toast.error("The business name needs at least 2 characters.");
      return;
    }
    if (clean === settings.business_name) return;
    save({ business_name: clean }, setSavingName, (s) => `Business name changed to ${s.business_name}.`);
  }

  function chooseStartPage(path) {
    setStartPage(path);
    setStartPageState(path);
    toast.success("Start page saved for this browser.");
  }

  async function doLogout() {
    await logout(); // the app switches to the sign-in page at "/" (see Login.jsx)
  }

  const canEdit = settings?.can_edit;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-500">Your account, your business and how this website looks for you.</p>
      </div>

      <Section title="Account" description="The account you signed in with.">
        <Row label="Signed in as">
          <span className="text-sm text-slate-900">{email ?? "–"}</span>
        </Row>
        <Row label="Session ends" hint="You are signed out automatically after this time.">
          <span className="text-sm text-slate-700">{expiresAt ? formatDateTime(new Date(expiresAt * 1000).toISOString()) : "–"}</span>
        </Row>
        <Row label="Demo user" hint="Who you are inside the business. Change it with the switcher in the top bar.">
          <span className="text-sm text-slate-700">
            {user.name} · {user.role === "owner" ? "Owner / Admin" : "Employee"}
          </span>
        </Row>
        <div className="flex justify-end border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={() => setConfirmLogout(true)}
            className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
          >
            Log out
          </button>
        </div>
      </Section>

      <Section
        title="Business"
        description={canEdit ? "Changes apply to everyone in this business and are written to the Activity Log." : "Only the owner can change these."}
      >
        {error ? (
          <p role="alert" className="text-sm text-red-600">{error}</p>
        ) : !settings ? (
          <Spinner label="Loading settings…" className="py-4" />
        ) : (
          <>
            <form onSubmit={saveName}>
              <Row label="Business name" hint="Shown in the top bar and on every page.">
                <div className="flex gap-2">
                  <label htmlFor="business-name" className="sr-only">Business name</label>
                  <input
                    id="business-name"
                    className={inputClass(false)}
                    value={name}
                    maxLength={120}
                    disabled={!canEdit || savingName}
                    onChange={(e) => setName(e.target.value)}
                  />
                  {canEdit && (
                    <button
                      type="submit"
                      disabled={savingName || name.trim() === settings.business_name}
                      className="shrink-0 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {savingName ? "Saving…" : "Save"}
                    </button>
                  )}
                </div>
              </Row>
            </form>

            <Row
              label="Prepare purchase order drafts automatically"
              hint={
                settings.auto_draft_server_enabled
                  ? "When stock runs low, a draft is prepared for the owner to approve. Off: use “Check restocking needs” instead."
                  : "Switched off for the whole server (AUTO_GENERATE_PO=false in .env)."
              }
            >
              <Toggle
                label="Prepare purchase order drafts automatically"
                checked={settings.auto_draft_orders && settings.auto_draft_server_enabled}
                disabled={!canEdit || savingDrafts || !settings.auto_draft_server_enabled}
                onChange={(value) =>
                  save({ auto_draft_orders: value }, setSavingDrafts, (s) =>
                    s.auto_draft_orders ? "Automatic drafts switched on." : "Automatic drafts switched off."
                  )
                }
              />
            </Row>

            <Row label="Currency and time zone" hint="Fixed for this version.">
              <span className="text-sm text-slate-700">Malaysian Ringgit (RM) · Malaysia time (UTC+8)</span>
            </Row>
          </>
        )}
      </Section>

      <Section title="Preferences" description="Saved in this browser only.">
        <Row label="Start page" hint="The page that opens after you sign in.">
          <label htmlFor="start-page" className="sr-only">Start page</label>
          <select
            id="start-page"
            value={startPage}
            onChange={(e) => chooseStartPage(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm sm:w-56"
          >
            {START_PAGES.map(([path, label]) => (
              <option key={path} value={path}>{label}</option>
            ))}
          </select>
        </Row>
      </Section>

      <Section title="About this demo">
        <Row label="Version">
          <span className="text-sm text-slate-700">{settings?.app_version ?? "–"}</span>
        </Row>
        <Row label="Business">
          <span className="text-sm text-slate-700">{business.name}</span>
        </Row>
        <p className="text-xs leading-relaxed text-slate-500">
          Hackathon MVP for the Orbyte Smart SME Challenge. All data is synthetic. The Orbyte integration is simulated:
          the sign-in and the user switcher stand in for Orbyte's own login. See the{" "}
          <Link to="/activity-logs" className="font-medium text-indigo-600 hover:text-indigo-800">Roles and permissions</Link>{" "}
          tab for who may do what (owner only).
        </p>
      </Section>

      {confirmLogout && (
        <ConfirmDialog
          title="Log out?"
          message="You will go back to the sign-in page. Unsaved changes on other pages are lost."
          confirmLabel="Log out"
          danger
          onConfirm={doLogout}
          onCancel={() => setConfirmLogout(false)}
        />
      )}
    </div>
  );
}
