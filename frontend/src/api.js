const API_HOST = process.env.REACT_APP_API_HOST || window.location.hostname;
const API_PORT = process.env.REACT_APP_API_PORT || "8000";
const API_BASE = `http://${API_HOST}:${API_PORT}/api`;

async function handleResponse(response) {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json();
}

export async function submitOrder({ tableId, items }) {
  const payload = {
    table_id: tableId ?? null,
    items: items.map(item => ({
      product_id: item.id,
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
