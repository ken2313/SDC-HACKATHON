// One small wrapper around fetch(). Every request:
//  - goes to /api/... (Vite forwards it to the FastAPI backend)
//  - carries the simulated Orbyte session header (X-User-Id)
//  - turns backend errors into readable messages
// No API keys live in the frontend. Secrets stay in the backend.

const USER_KEY = "orbyte_demo_user_id";

export function getStoredUserId() {
  try {
    return localStorage.getItem(USER_KEY);
  } catch {
    return null;
  }
}

export function setStoredUserId(id) {
  try {
    localStorage.setItem(USER_KEY, String(id));
  } catch {
    /* storage can be blocked; the app still works for this session */
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function buildQuery(params) {
  if (!params) return "";
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "" && value !== false) {
      query.append(key, String(value));
    }
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

// FastAPI sends errors as {detail: "text"} or, for validation errors,
// {detail: [{loc: [...], msg: "..."}]}.
function extractMessage(data, status) {
  if (data && typeof data.detail === "string") return data.detail;
  if (data && Array.isArray(data.detail)) {
    return data.detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join(" • ");
  }
  return `Request failed (HTTP ${status}).`;
}

export async function request(path, { method = "GET", body, params } = {}) {
  const headers = { "Content-Type": "application/json" };
  const userId = getStoredUserId();
  if (userId) headers["X-User-Id"] = userId;

  let response;
  try {
    response = await fetch(`/api${path}${buildQuery(params)}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Cannot reach the server. Check that the backend is running.", 0);
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(extractMessage(data, response.status), response.status);
  return data;
}
