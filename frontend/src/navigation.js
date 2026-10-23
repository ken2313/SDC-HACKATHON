// The 10 main navigation items from the project brief.
// `live: true` means the page is built. Others show a "coming in Feature N" page
// so the full structure is visible while we build one feature at a time.
export const NAV_ITEMS = [
  { label: "Dashboard", path: "/dashboard", live: true, feature: 7 },
  { label: "Inventory", path: "/inventory", live: true, feature: 1 },
  { label: "Stock Alerts", path: "/stock-alerts", live: true, feature: 2 },
  { label: "Purchase Orders", path: "/purchase-orders", live: true, feature: 3 },
  { label: "Supplier Orders", path: "/supplier-orders", live: true, feature: 5 },
  { label: "Suppliers", path: "/suppliers", live: true, feature: 6 },
  { label: "Demand Forecasting", path: "/forecasting", live: false, feature: 8,
    description: "Moving-average demand forecasts, run-out estimates and recommended reorder dates." },
  { label: "AI Anomaly Detection", path: "/anomalies", live: false, feature: 9,
    description: "A small PyTorch model running on a RunPod GPU flags unusual stock movements for human review." },
  { label: "Activity Logs", path: "/activity-logs", live: true, feature: 4,
    permission: "logs:view" }, // owner only: the sidebar hides it for employees, the backend enforces it
  { label: "Settings", path: "/settings", live: false, feature: null,
    description: "Business and notification settings. Planned for after the core features." },
];
