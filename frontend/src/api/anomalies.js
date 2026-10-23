// Feature 9: AI anomaly flags. The AI runs on a RunPod GPU behind the backend;
// the frontend only talks to our own backend (no AI keys or URLs here).
import { request } from "./client";

// state: "open" | "reviewed" | "all"   results: "flags" | "all"
export function listAnomalies({ state = "open", results = "flags" } = {}) {
  return request("/anomalies", { params: { state, results } });
}

export function getAiStatus() {
  return request("/anomalies/status");
}

export function reviewAnomaly(id, note) {
  return request(`/anomalies/${id}/review`, { method: "POST", body: { note } });
}