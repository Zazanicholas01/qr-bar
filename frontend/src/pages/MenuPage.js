import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useCart } from "../context/CartContext";
import { autoLogin, submitOrder, updateUser } from "../api";

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
  const [userId, setUserId] = useState(null);
  const [userInfo, setUserInfo] = useState({ name: "", email: "", phone: "", age: "" });
  const [isSavingInfo, setIsSavingInfo] = useState(false);
  const [infoFeedback, setInfoFeedback] = useState(null);
  const [userError, setUserError] = useState(null);
  const [isAuthenticating, setIsAuthenticating] = useState(true);

  const apiHost = process.env.REACT_APP_API_HOST || window.location.hostname;
  const envPort = process.env.REACT_APP_API_PORT;
  const apiProtocol =
    process.env.REACT_APP_API_PROTOCOL ||
    (typeof window !== "undefined" && window.location.protocol
      ? window.location.protocol
      : "http:");
  const detectedPort = typeof window !== "undefined" ? window.location.port : "";
  const apiPort = envPort !== undefined ? envPort : detectedPort;
  const isDefaultPort =
    !apiPort ||
    (apiProtocol.startsWith("https") && apiPort === "443") ||
    (apiProtocol.startsWith("http") && apiPort === "80");
  const portSegment = isDefaultPort ? "" : `:${apiPort}`;
  const menuUrl = `${apiProtocol}//${apiHost}${portSegment}/api/menu?table_id=${tableId}`;

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

  useEffect(() => {
    let isMounted = true;
    setIsAuthenticating(true);
    setUserError(null);
    setUserId(null);

    autoLogin(tableId)
      .then(user => {
        if (isMounted) {
          setUserId(user.id);
          setUserInfo({
            name: user.name || "",
            email: user.email || "",
            phone: user.phone || "",
            age: user.age != null ? String(user.age) : "",
          });
        }
      })
      .catch(err => {
        if (isMounted) {
          setUserError(err.message || "Impossibile avviare la sessione utente.");
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsAuthenticating(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [tableId]);

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
    "Espresso Macchiato": "Un tocco di latte montato per un finale vellutato.",
    Cappuccino: "Latte montato setoso con spolverata di cacao amaro.",
    "Latte Macchiato": "Strati di latte e caffè per un sorso equilibrato.",
    "Caffè Americano": "Più lungo e delicato, perfetto per un sorso prolungato.",
    "Succo d'arancia": "Spremuto fresco ogni mattina per la giusta carica.",
    "Acqua frizzante": "Leggera e frizzante, perfetta per accompagnare ogni piatto.",
    "Acqua naturale": "Naturale e bilanciata, servita fresca.",
    "Tè freddo": "Infuso alla pesca, servito con ghiaccio.",
    "Vino bianco": "Selezione del giorno, aroma floreale e finale minerale.",
    "Vino rosso": "Rosso intenso con note di frutti di bosco.",
    "Birra artigianale": "Prodotta localmente, gusto deciso e profumo di luppolo.",
    Spritz: "Classico veneziano con prosecco, Aperol e una fetta d'arancia.",
    Negroni: "Un grande classico italiano equilibrato e aromatico.",
    Mojito: "Rum bianco, lime e menta fresca per un drink iconico.",
    "Espresso Martini": "Vodka, espresso e liquore al caffè per un finale energizzante.",
  };

  const categories = menu.categories && menu.categories.length
    ? menu.categories
    : [
        {
          name: "Menu",
          items: menu.items || [],
        },
      ];

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
      const order = await submitOrder({
        tableId: menu.table_id,
        userId,
        items: cartItems,
      });

      setOrderFeedback({
        type: "success",
        message: `Ordine #${order.id} ricevuto (utente ${order.user_id ?? "ospite"}). Il barista è stato avvisato!`,
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

  const handleInfoChange = event => {
    const { name, value } = event.target;
    setUserInfo(prev => ({ ...prev, [name]: value }));
  };

  const handleInfoSubmit = async event => {
    event.preventDefault();
    if (!userId) {
      return;
    }
    setIsSavingInfo(true);
    setInfoFeedback(null);
    try {
      const payload = {};
      if (userInfo.name.trim()) payload.name = userInfo.name.trim();
      if (userInfo.email.trim()) payload.email = userInfo.email.trim();
      if (userInfo.phone.trim()) payload.phone = userInfo.phone.trim();
      if (userInfo.age.trim()) {
        const ageNumber = Number.parseInt(userInfo.age, 10);
        if (!Number.isNaN(ageNumber)) {
          payload.age = ageNumber;
        }
      }

      if (Object.keys(payload).length === 0) {
        setInfoFeedback({ type: "error", message: "Inserisci almeno un dato." });
      } else {
        await updateUser(userId, payload);
        setInfoFeedback({ type: "success", message: "Dati salvati." });
      }
    } catch (err) {
      setInfoFeedback({
        type: "error",
        message: err.message || "Impossibile salvare i dati.",
      });
    } finally {
      setIsSavingInfo(false);
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
        <article className="info-card">
          <h2>I tuoi dati (opzionali)</h2>
          <p style={{ marginBottom: "1rem", color: "rgba(27, 27, 27, 0.7)" }}>
            Inserisci i tuoi dati per un servizio più rapido. Puoi saltare questo passaggio se preferisci restare anonimo.
          </p>
          <form className="info-form" onSubmit={handleInfoSubmit}>
            <div className="info-grid">
              <label>
                Nome
                <input
                  type="text"
                  name="name"
                  value={userInfo.name}
                  onChange={handleInfoChange}
                  placeholder="Nome e cognome"
                />
              </label>
              <label>
                Email
                <input
                  type="email"
                  name="email"
                  value={userInfo.email}
                  onChange={handleInfoChange}
                  placeholder="email@example.com"
                />
              </label>
              <label>
                Telefono
                <input
                  type="tel"
                  name="phone"
                  value={userInfo.phone}
                  onChange={handleInfoChange}
                  placeholder="Numero di telefono"
                />
              </label>
              <label>
                Età
                <input
                  type="number"
                  name="age"
                  min="0"
                  max="120"
                  value={userInfo.age}
                  onChange={handleInfoChange}
                  placeholder="Età"
                />
              </label>
            </div>
            {infoFeedback && (
              <p className={`info-feedback info-feedback-${infoFeedback.type}`}>
                {infoFeedback.message}
              </p>
            )}
            <button type="submit" className="info-save" disabled={isSavingInfo || !userId}>
              {isSavingInfo ? "Salvataggio..." : "Salva i miei dati"}
            </button>
          </form>
        </article>

        <div className="status-card">
          Seleziona un&apos;esperienza dal nostro bancone virtuale. Ordinazioni
          disponibili direttamente dall&apos;app.
        </div>

        {categories.map(category => (
          <section className="menu-category" key={category.name}>
            <h2 className="menu-category-title">{category.name}</h2>
            <div className="menu-grid">
              {category.items.map(item => (
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
          </section>
        ))}

        <aside className="cart-panel">
          <h2>Il tuo ordine</h2>
          {isAuthenticating && (
            <p className="cart-feedback cart-feedback-neutral">Stiamo preparando la tua sessione...</p>
          )}
          {userError && (
            <p className="cart-feedback cart-feedback-error">{userError}</p>
          )}
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
                disabled={
                  cartItems.length === 0 ||
                  isSubmitting ||
                  isAuthenticating ||
                  !userId ||
                  Boolean(userError)
                }
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
