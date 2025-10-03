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
    return (
      <section className="main-content">
        <div className="status-card">Unable to load menu: {error}</div>
      </section>
    );
  }

  if (!menu) {
    return (
      <section className="main-content">
        <div className="status-card">Loading menu...</div>
      </section>
    );
  }

  const descriptions = {
    Espresso: "Estratto in 25 secondi con miscela arabica al 70%.",
    Cappuccino: "Latte montato setoso con spolverata di cacao amaro.",
    Cornetto: "Sfoglia francese dorata ogni mattina nel nostro laboratorio.",
  };

  return (
    <>
      <header>
        <h1>Menu digitale</h1>
        <p style={{ marginTop: "0.35rem", opacity: 0.8 }}>
          Tavolo {menu.table_id}
        </p>
      </header>
      <section className="main-content">
        <div className="status-card">
          Seleziona un&apos;esperienza dal nostro bancone virtuale. Ordinazioni
          disponibili direttamente dall&apos;app.
        </div>

        <div className="menu-grid">
          {menu.items.map(item => (
            <article className="menu-item" key={item.id}>
              <div className="menu-item-header">
                <span className="menu-item-name">{item.name}</span>
                <span className="menu-item-price">€ {item.price.toFixed(2)}</span>
              </div>
              <p className="menu-item-note">
                {descriptions[item.name] ||
                  "Preparato con ingredienti freschi e selezionati per la tua pausa."}
              </p>
            </article>
          ))}
        </div>
      </section>
      <footer>
        Vuoi ordinare qualcos&apos;altro? Basta mostrare questo schermo al barista.
      </footer>
    </>
  );
}

export default MenuPage;
