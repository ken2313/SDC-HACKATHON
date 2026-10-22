import { request } from "./client.js";

// Alerts are created and resolved automatically by the backend,
// so the frontend can only read them. (Thresholds change through inventoryApi.update.)
export const alertsApi = {
  list: (status = "open") => request("/alerts", { params: { status } }),
  summary: () => request("/alerts/summary"),
};
