import { request } from "./client.js";

// The Activity Log is READ-ONLY here. Entries are written by the backend when something
// happens, and only the owner may read them (the backend checks this, not the page).
export const activityLogsApi = {
  list: (params) => request("/activity-logs", { params }),
  summary: () => request("/activity-logs/summary"),
  filters: () => request("/activity-logs/filters"),
};

// Who may do what. Any signed-in user can read the rules.
export const accessApi = {
  matrix: () => request("/access/matrix"),
};
