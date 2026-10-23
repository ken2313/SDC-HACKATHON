import { request } from "./client.js";

// Demand forecasting (Feature 8). Read-only: forecasts are calculated by the backend from
// the stock movement history. Changing a reorder level uses the inventory API (owner only).
export const forecastsApi = {
  list: () => request("/forecasts"),
  get: (itemId, horizonDays = 14) => request(`/forecasts/${itemId}`, { params: { horizon_days: horizonDays } }),
};
