const API_HOST = process.env.REACT_APP_API_HOST || window.location.hostname;
const envPort = process.env.REACT_APP_API_PORT;
const API_PORT = envPort === undefined ? "8000" : envPort;
const API_PROTOCOL =
  process.env.REACT_APP_API_PROTOCOL ||
  (typeof window !== "undefined" && window.location.protocol ? window.location.protocol : "http:");

const portSegment = API_PORT ? `:${API_PORT}` : "";
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
