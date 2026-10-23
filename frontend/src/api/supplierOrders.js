import { request } from "./client.js";

// Supplier order tracking. The backend decides who may do what:
//  - owner AND employee: mark shipped / delayed, confirm a delivery
//  - owner only: place an approved order with the supplier (simulated), cancel
export const supplierOrdersApi = {
  list: (view = "active") => request("/supplier-orders", { params: { view } }),
  summary: () => request("/supplier-orders/summary"),
  place: (id) => request(`/supplier-orders/${id}/place`, { method: "POST" }),
  updateStatus: (id, payload) => request(`/supplier-orders/${id}/status`, { method: "POST", body: payload }),
  receive: (id, payload) => request(`/supplier-orders/${id}/receive`, { method: "POST", body: payload }),
  cancel: (id, reason) => request(`/supplier-orders/${id}/cancel`, { method: "POST", body: { reason } }),
};
