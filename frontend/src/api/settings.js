import { request } from "./client.js";

// Business settings. Everyone can read them; only the owner can change them (backend-checked).
export const settingsApi = {
  get: () => request("/settings"),
  update: (payload) => request("/settings", { method: "PATCH", body: payload }),
};
