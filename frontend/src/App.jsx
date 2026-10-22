import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Spinner from "./components/Spinner.jsx";
import { SessionProvider, useSession } from "./context/SessionContext.jsx";
import { ToastProvider } from "./context/ToastContext.jsx";
import { NAV_ITEMS } from "./navigation.js";
import ComingSoon from "./pages/ComingSoon.jsx";
import Inventory from "./pages/Inventory.jsx";
import PurchaseOrders from "./pages/PurchaseOrders.jsx";
import StockAlerts from "./pages/StockAlerts.jsx";

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
        <Route index element={<Navigate to="/inventory" replace />} />
        {/* key={user.id} reloads the page's data when the demo user is switched */}
        <Route path="inventory" element={<Inventory key={user.id} />} />
        <Route path="stock-alerts" element={<StockAlerts key={user.id} />} />
        <Route path="purchase-orders" element={<PurchaseOrders key={user.id} />} />
        {NAV_ITEMS.filter((item) => !item.live).map((item) => (
          <Route
            key={item.path}
            path={item.path.slice(1)}
            element={<ComingSoon title={item.label} feature={item.feature} description={item.description} />}
          />
        ))}
        <Route path="*" element={<Navigate to="/inventory" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <SessionProvider>
        <AppRoutes />
      </SessionProvider>
    </ToastProvider>
  );
}
