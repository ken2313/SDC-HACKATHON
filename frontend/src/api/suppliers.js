import { request } from "./client.js";

// Supplier management (Feature 6). The backend decides who may do what:
//  - owner AND employee: view suppliers, contacts, price lists and order history
//  - owner only: add / edit / deactivate suppliers and change the price list
// There is no delete: a supplier's order history must stay, so it is deactivated instead.
export const suppliersApi = {
  list: (params) => request("/suppliers", { params }),
  summary: () => request("/suppliers/summary"),
  withoutSupplier: () => request("/suppliers/products-without-supplier"),
  get: (id) => request(`/suppliers/${id}`),
  create: (payload) => request("/suppliers", { method: "POST", body: payload }),
  update: (id, payload) => request(`/suppliers/${id}`, { method: "PATCH", body: payload }),
  deactivate: (id) => request(`/suppliers/${id}/deactivate`, { method: "POST" }),
  activate: (id) => request(`/suppliers/${id}/activate`, { method: "POST" }),
  addProduct: (id, payload) => request(`/suppliers/${id}/products`, { method: "POST", body: payload }),
  updateProduct: (id, linkId, payload) =>
    request(`/suppliers/${id}/products/${linkId}`, { method: "PATCH", body: payload }),
  removeProduct: (id, linkId) => request(`/suppliers/${id}/products/${linkId}`, { method: "DELETE" }),
};
