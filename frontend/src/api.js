const API_HOST = process.env.REACT_APP_API_HOST || window.location.hostname;
const envPort = process.env.REACT_APP_API_PORT;
const API_PROTOCOL =
  process.env.REACT_APP_API_PROTOCOL ||
  (typeof window !== "undefined" && window.location.protocol ? window.location.protocol : "http:");

// Prefer explicit env port; otherwise use the current location's port (often empty on 80/443)
const detectedPort = typeof window !== "undefined" ? window.location.port : "";
const API_PORT = envPort !== undefined ? envPort : detectedPort;

// Omit standard ports for scheme to keep same-origin requests
const isDefaultPort =
  !API_PORT ||
  (API_PROTOCOL.startsWith("https") && API_PORT === "443") ||
  (API_PROTOCOL.startsWith("http") && API_PORT === "80");
const portSegment = isDefaultPort ? "" : `:${API_PORT}`;

const API_BASE = `${API_PROTOCOL}//${API_HOST}${portSegment}/api`;

async function handleResponse(response) {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json();
}

export async function submitOrder({ tableId, items, userId }) {
  const payload = {
    table_id: tableId ?? null,
    user_id: userId ?? null,
    items: items.map(item => ({
      product_id: item.id,
      name: item.name,
      unit_price: item.price,
      quantity: item.quantity,
    })),
  };

  const response = await fetch(`${API_BASE}/orders/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleResponse(response);
}

export async function autoLogin(tableId) {
  const search = tableId ? `?table_id=${encodeURIComponent(tableId)}` : "";
  const response = await fetch(`${API_BASE}/users/auto${search}`, {
    method: "POST",
  });

  return handleResponse(response);
}

export async function updateUser(userId, payload) {
  const response = await fetch(`${API_BASE}/users/${userId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleResponse(response);
}

export async function searchMenu(query, limit = 5) {
  const search = new URLSearchParams({ q: query, limit: String(limit) });
  const response = await fetch(`${API_BASE}/ai/search?${search.toString()}`);
  return handleResponse(response);
}

export async function fetchItemTags() {
  const response = await fetch(`${API_BASE}/ai/tags`);
  return handleResponse(response);
}

export async function signInWithGoogle(credential, tableId) {
  const response = await fetch(`${API_BASE}/auth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential, table_id: tableId ?? null }),
  });
  return handleResponse(response);
}

export async function registerUser({ email, password, name, surname, tableId }) {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name: name ?? null, surname: surname ?? null, table_id: tableId ?? null }),
  });
  return handleResponse(response);
}

export async function loginUser({ email, password, tableId }) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, table_id: tableId ?? null }),
  });
  return handleResponse(response);
}

export async function fetchAuthConfig() {
  const response = await fetch(`${API_BASE}/auth/config`);
  return handleResponse(response);
}

export async function fetchSession() {
  const response = await fetch(`${API_BASE}/auth/session`);
  if (response.status === 204) return null;
  // When not logged in, FastAPI returns null JSON
  if (response.status === 200) return response.json();
  return null;
}

export async function startPasswordReset(email) {
  const response = await fetch(`${API_BASE}/auth/password/reset/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return handleResponse(response);
}

export async function startEmailVerification(email) {
  const response = await fetch(`${API_BASE}/auth/email/verify/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return handleResponse(response);
}
