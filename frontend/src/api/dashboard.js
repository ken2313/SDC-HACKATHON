import { request } from "./client.js";

// Inventory dashboard (Feature 7). Read-only. Every number comes from the backend database.
// Money totals are only sent to roles with "reports:view" (the owner); others get null.
export const dashboardApi = {
  overview: () => request("/dashboard"),
  trend: (itemId, days = 30) => request("/dashboard/trend", { params: { item_id: itemId, days } }),
};
