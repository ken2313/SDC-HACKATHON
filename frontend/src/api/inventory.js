import { request } from "./client.js";

export const inventoryApi = {
  list: (params) => request("/inventory", { params }),
  summary: () => request("/inventory/summary"),
  categories: () => request("/inventory/categories"),
  create: (payload) => request("/inventory", { method: "POST", body: payload }),
  update: (id, payload) => request(`/inventory/${id}`, { method: "PATCH", body: payload }),
  archive: (id) => request(`/inventory/${id}/archive`, { method: "POST" }),
  restore: (id) => request(`/inventory/${id}/restore`, { method: "POST" }),
  recordMovement: (id, payload) => request(`/inventory/${id}/movements`, { method: "POST", body: payload }),
  movements: (id) => request(`/inventory/${id}/movements`),
};

// SIMULATED Orbyte layer (not an official Orbyte API)
export const orbyteApi = {
  listDemoUsers: () => request("/orbyte-mock/users"),
  getContext: () => request("/orbyte-mock/context"),
};
