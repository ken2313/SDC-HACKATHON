import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { inputClass } from "../components/FormField.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { getStartPage } from "../utils/preferences.js";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// The first page: sign in to the demo workspace. The backend checks the details.
export default function Login() {
  const { login, notice } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [busy, setBusy] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // The sign-in page is the main page: always show it at "/"
  useEffect(() => {
    if (location.pathname !== "/") navigate("/", { replace: true });
  }, [location.pathname, navigate]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const found = {};
    if (!EMAIL_PATTERN.test(email.trim())) found.email = "Enter your email address.";
    if (!password) found.password = "Enter your password.";
    setErrors(found);
    if (Object.keys(found).length) return;

    setBusy(true);
    setServerError(null);
    try {
      await login(email.trim(), password);
      navigate(getStartPage(), { replace: true }); // the app opens on the chosen start page
    } catch (error) {
      setServerError(error.status === 0 ? "Cannot reach the server. Check that the backend is running." : error.message);
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-900 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-3 text-white">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500 text-base font-bold">SI</div>
          <div>
            <p className="text-lg font-semibold leading-tight">Smart Inventory</p>
            <p className="text-sm text-slate-300">Supplier Order Management</p>
          </div>
        </div>

        <div className="rounded-2xl bg-white p-6 shadow-2xl sm:p-8">
          <h1 className="text-xl font-semibold text-slate-900">Sign in</h1>
          <p className="mt-1 text-sm text-slate-500">Use your business account to open the inventory module.</p>

          {notice && !serverError && (
            <p role="status" className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
              {notice}
            </p>
          )}
          {serverError && (
            <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {serverError}
            </p>
          )}

          <form onSubmit={handleSubmit} noValidate className="mt-5 space-y-4">
            <div>
              <label htmlFor="login-email" className="mb-1 block text-sm font-medium text-slate-700">Email</label>
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                className={inputClass(errors.email)}
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setErrors((current) => ({ ...current, email: undefined }));
                }}
                placeholder="you@business.com"
                autoFocus
              />
              {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email}</p>}
            </div>

            <div>
              <label htmlFor="login-password" className="mb-1 block text-sm font-medium text-slate-700">Password</label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  className={`${inputClass(errors.password)} pr-16`}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setErrors((current) => ({ ...current, password: undefined }));
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute inset-y-0 right-0 px-3 text-xs font-medium text-indigo-600 hover:text-indigo-800"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {errors.password && <p className="mt-1 text-xs text-red-600">{errors.password}</p>}
            </div>

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs leading-relaxed text-slate-400">
          Hackathon demo for the Orbyte Smart SME Challenge. All data is synthetic and the Orbyte integration is simulated.
        </p>
      </div>
    </div>
  );
}
