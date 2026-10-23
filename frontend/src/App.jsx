import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Spinner from "./components/Spinner.jsx";
import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import { SessionProvider, useSession } from "./context/SessionContext.jsx";
import { ToastProvider } from "./context/ToastContext.jsx";
import { NAV_ITEMS } from "./navigation.js";
import ActivityLogs from "./pages/ActivityLogs.jsx";
import AnomalyDetection from "./pages/AnomalyDetection.jsx";
import ComingSoon from "./pages/ComingSoon.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Forecasting from "./pages/Forecasting.jsx";
import Inventory from "./pages/Inventory.jsx";
import Login from "./pages/Login.jsx";
import PurchaseOrders from "./pages/PurchaseOrders.jsx";
import Settings from "./pages/Settings.jsx";
import StockAlerts from "./pages/StockAlerts.jsx";
import SupplierOrders from "./pages/SupplierOrders.jsx";
import Suppliers from "./pages/Suppliers.jsx";
import { getStartPage } from "./utils/preferences.js";

function AppRoutes() {
  const { status, error, retry, user } = useSession();

  if (status === "loading") {
    return <Spinner label="Connecting to the server…" className="min-h-screen" />;
  }

  if (status === "error") {
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <h1 className="text-lg font-semibold text-slate-900">Cannot connect to the backend</h1>
        <p className="mt-2 text-sm text-slate-600">{error}</p>
        <p className="mt-2 text-sm text-slate-500">Make sure the FastAPI server is running on port 8000, then try again.</p>
        <button
          type="button"
          onClick={retry}
          className="mt-5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to={getStartPage()} replace />} />
        {/* key={user.id} reloads the page's data when the demo user is switched */}
        <Route path="dashboard" element={<Dashboard key={user.id} />} />
        <Route path="inventory" element={<Inventory key={user.id} />} />
        <Route path="stock-alerts" element={<StockAlerts key={user.id} />} />
        <Route path="purchase-orders" element={<PurchaseOrders key={user.id} />} />
        <Route path="supplier-orders" element={<SupplierOrders key={user.id} />} />
        <Route path="suppliers" element={<Suppliers key={user.id} />} />
        <Route path="forecasting" element={<Forecasting key={user.id} />} />
        <Route path="anomalies" element={<AnomalyDetection key={user.id} />} />
        <Route path="settings" element={<Settings key={user.id} />} />
        <Route path="activity-logs" element={<ActivityLogs key={user.id} />} />
        {NAV_ITEMS.filter((item) => !item.live).map((item) => (
          <Route
            key={item.path}
            path={item.path.slice(1)}
            element={<ComingSoon title={item.label} feature={item.feature} description={item.description} />}
          />
        ))}
        <Route path="*" element={<Navigate to={getStartPage()} replace />} />
      </Route>
    </Routes>
  );
}

// Signed out: only the sign-in page. Signed in: the simulated Orbyte session and the app.
function AuthGate() {
  const { status, notice } = useAuth();
  if (status === "checking") return <Spinner label="Checking your session…" className="min-h-screen" />;
  if (status === "error") {
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <h1 className="text-lg font-semibold text-slate-900">Cannot connect to the backend</h1>
        <p className="mt-2 text-sm text-slate-600">{notice}</p>
        <p className="mt-2 text-sm text-slate-500">Make sure the FastAPI server is running on port 8000, then reload the page.</p>
      </div>
    );
  }
  if (status !== "signed_in") {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }
  return (
    <SessionProvider>
      <AppRoutes />
    </SessionProvider>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <AuthGate />
      </AuthProvider>
    </ToastProvider>
  );
}