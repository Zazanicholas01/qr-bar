import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

function MenuPage() {
  const { tableId } = useParams();
  const [menu, setMenu] = useState(null);
  const [error, setError] = useState(null);

  const apiHost = process.env.REACT_APP_API_HOST || window.location.hostname;
  const apiPort = process.env.REACT_APP_API_PORT || "8000";
  const menuUrl = `http://${apiHost}:${apiPort}/api/menu?table_id=${tableId}`;

  useEffect(() => {
    setError(null);
    setMenu(null);

    fetch(menuUrl)
      .then(res => {
        if (!res.ok) {
          throw new Error(`Request failed with status ${res.status}`);
        }
        return res.json();
      })
      .then(data => setMenu(data))
      .catch(err => setError(err.message));
  }, [menuUrl, tableId]);

  if (error) {
    return <p style={{ padding: "1rem", color: "red" }}>Unable to load menu: {error}</p>;
  }

  if (!menu) return <p style={{ padding: "1rem" }}>Loading menu...</p>;

  return (
    <main style={{ padding: "1.5rem", fontFamily: "sans-serif" }}>
      <h2 style={{ marginBottom: "1rem" }}>Table {menu.table_id}</h2>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {menu.items.map(item => (
          <li
            key={item.id}
            style={{
              border: "1px solid #ddd",
              borderRadius: "8px",
              padding: "0.75rem 1rem",
              marginBottom: "0.75rem",
              boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
            }}
          >
            <div style={{ fontWeight: "600" }}>{item.name}</div>
            <div style={{ color: "#555" }}>€ {item.price.toFixed(2)}</div>
          </li>
        ))}
      </ul>
    </main>
  );
}

export default MenuPage;
