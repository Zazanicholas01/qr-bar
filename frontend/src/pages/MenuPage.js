import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

function MenuPage() {
  const { tableId } = useParams();
  const [menu, setMenu] = useState(null);

  useEffect(() => {
    fetch(`http://localhost:8000/api/menu?table_id=${tableId}`)
      .then(res => res.json())
      .then(data => setMenu(data));
  }, [tableId]);

  if (!menu) return <p>Loading menu...</p>;

  return (
    <div>
      <h2>Table {menu.table_id}</h2>
      <ul>
        {menu.items.map((item, idx) => (
          <li key={idx}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default MenuPage;
