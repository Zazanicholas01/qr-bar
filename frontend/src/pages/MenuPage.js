import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useCart } from "../context/CartContext";
import { submitOrder } from "../api";

function MenuPage() {
  const { tableId } = useParams();
  const [menu, setMenu] = useState(null);
  const [error, setError] = useState(null);
  const {
    items: cartItems,
    addItem,
    updateQuantity,
    removeItem,
    clearCart,
    totalAmount,
    totalQuantity,
  } = useCart();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [orderFeedback, setOrderFeedback] = useState(null);

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

  const handleAddToCart = item => {
    addItem({
      id: item.id,
      name: item.name,
      price: item.price,
    });
  };

  const handleDecrease = itemId => {
    const existing = cartItems.find(line => line.id === itemId);
    if (!existing) {
      return;
    }
    updateQuantity(itemId, existing.quantity - 1);
  };

  const handleIncrease = itemId => {
    const existing = cartItems.find(line => line.id === itemId);
    const nextQuantity = existing ? existing.quantity + 1 : 1;
    updateQuantity(itemId, nextQuantity);
  };

  const formatPrice = value => value.toFixed(2);

  const handleCheckout = async () => {
    if (cartItems.length === 0 || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setOrderFeedback(null);

    try {
      const response = await submitOrder({
        tableId: menu.table_id,
        items: cartItems,
      });

      setOrderFeedback({
        type: "success",
        message: `Ordine #${response.order.id} ricevuto. Il barista è stato avvisato!`,
      });
      clearCart();
    } catch (error) {
      setOrderFeedback({
        type: "error",
        message: error.message || "Impossibile inviare l'ordine. Riprova tra poco.",
      });
    } finally {
      setIsSubmitting(false);
    }
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
                <span className="menu-item-price">€ {formatPrice(item.price)}</span>
              </div>
              <p className="menu-item-note">
                {descriptions[item.name] ||
                  "Preparato con ingredienti freschi e selezionati per la tua pausa."}
              </p>
              <button
                type="button"
                className="menu-item-add"
                onClick={() => handleAddToCart(item)}
              >
                Aggiungi al carrello
              </button>
            </article>
          ))}
        </div>

        <aside className="cart-panel">
          <h2>Il tuo ordine</h2>
          {cartItems.length === 0 ? (
            <p className="cart-empty">Il carrello è vuoto.</p>
          ) : (
            <>
              <ul className="cart-list">
                {cartItems.map(item => (
                  <li className="cart-item" key={item.id}>
                    <div className="cart-item-info">
                      <span className="cart-item-name">{item.name}</span>
                      <span className="cart-item-price">
                        € {formatPrice(item.price * item.quantity)}
                      </span>
                    </div>
                    <div className="cart-item-controls">
                      <button
                        type="button"
                        className="cart-quantity-btn"
                        onClick={() => handleDecrease(item.id)}
                      >
                        -
                      </button>
                      <span className="cart-quantity-value">{item.quantity}</span>
                      <button
                        type="button"
                        className="cart-quantity-btn"
                        onClick={() => handleIncrease(item.id)}
                      >
                        +
                      </button>
                    </div>
                    <button
                      type="button"
                      className="cart-remove"
                      onClick={() => removeItem(item.id)}
                    >
                      Rimuovi
                    </button>
                  </li>
                ))}
              </ul>
              <div className="cart-summary">
                <div>
                  <span>Articoli:</span>
                  <span>{totalQuantity}</span>
                </div>
                <div>
                  <span>Totale:</span>
                  <span>€ {formatPrice(totalAmount)}</span>
                </div>
              </div>
              {orderFeedback && (
                <p className={`cart-feedback cart-feedback-${orderFeedback.type}`}>
                  {orderFeedback.message}
                </p>
              )}
              <button
                type="button"
                className="cart-checkout"
                onClick={handleCheckout}
                disabled={cartItems.length === 0 || isSubmitting}
              >
                {isSubmitting ? "Invio in corso..." : "Invia ordine"}
              </button>
            </>
          )}
        </aside>
      </section>
      <footer>
        Vuoi ordinare qualcos&apos;altro? Basta mostrare questo schermo al barista.
      </footer>
    </>
  );
}

export default MenuPage;
