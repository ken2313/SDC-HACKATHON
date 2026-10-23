import { request } from "./client.js";

// Orders are PREPARED by the system or by staff, but only the owner can approve or reject.
// The backend enforces this: hiding a button in the page is not what protects it.
export const purchaseOrdersApi = {
  list: (status = "all") => request("/purchase-orders", { params: { status } }),
  summary: () => request("/purchase-orders/summary"),
  needs: () => request("/purchase-orders/needs"),
  generate: () => request("/purchase-orders/generate", { method: "POST" }),
  get: (id) => request(`/purchase-orders/${id}`),
  update: (id, payload) => request(`/purchase-orders/${id}`, { method: "PATCH", body: payload }),
  removeLine: (id, lineId) => request(`/purchase-orders/${id}/lines/${lineId}`, { method: "DELETE" }),
  approve: (id) => request(`/purchase-orders/${id}/approve`, { method: "POST" }),
  reject: (id, reason) => request(`/purchase-orders/${id}/reject`, { method: "POST", body: { reason } }),
};
