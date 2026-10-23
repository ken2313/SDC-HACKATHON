// Display preferences for THIS browser only (not shared, not sent to the server).
const START_PAGE_KEY = "orbyte_start_page";

export const START_PAGES = [
  ["/dashboard", "Dashboard"],
  ["/inventory", "Inventory"],
  ["/stock-alerts", "Stock Alerts"],
  ["/purchase-orders", "Purchase Orders"],
  ["/forecasting", "Demand Forecasting"],
];

export function getStartPage() {
  try {
    const saved = localStorage.getItem(START_PAGE_KEY);
    return START_PAGES.some(([path]) => path === saved) ? saved : "/dashboard";
  } catch {
    return "/dashboard";
  }
}

export function setStartPage(path) {
  try {
    localStorage.setItem(START_PAGE_KEY, path);
  } catch {
    /* storage blocked: the default start page is used */
  }
}
