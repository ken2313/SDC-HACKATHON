// The 10 main navigation items from the project brief.
// `live: true` means the page is built. Others show a "coming in Feature N" page
// so the full structure is visible while we build one feature at a time.
export const NAV_ITEMS = [
  { label: "Dashboard", path: "/dashboard", live: false, feature: 7,
    description: "Summary cards, charts, recent activity and upcoming deliveries, all read from the database." },
  { label: "Inventory", path: "/inventory", live: true, feature: 1 },
  { label: "Stock Alerts", path: "/stock-alerts", live: true, feature: 2 },
  { label: "Purchase Orders", path: "/purchase-orders", live: false, feature: 3,
    description: "Draft purchase orders generated for products that need restocking. The owner reviews, edits, approves or rejects." },
  { label: "Supplier Orders", path: "/supplier-orders", live: false, feature: 5,
    description: "Track orders from Draft to Delivered, spot overdue deliveries and update inventory when goods arrive." },
  { label: "Suppliers", path: "/suppliers", live: false, feature: 6,
    description: "Supplier contacts, product prices, typical delivery times and order history." },
  { label: "Demand Forecasting", path: "/forecasting", live: false, feature: 8,
    description: "Moving-average demand forecasts, run-out estimates and recommended reorder dates." },
  { label: "AI Anomaly Detection", path: "/anomalies", live: false, feature: 9,
    description: "A small PyTorch model running on a RunPod GPU flags unusual stock movements for human review." },
  { label: "Activity Logs", path: "/activity-logs", live: false, feature: 4,
    description: "Who did what and when, with previous and updated values. (Logging is already recording in the background.)" },
  { label: "Settings", path: "/settings", live: false, feature: null,
    description: "Business and notification settings. Planned for after the core features." },
];
