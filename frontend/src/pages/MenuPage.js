import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useCart } from "../context/CartContext";
import { autoLogin, submitOrder, updateUser, searchMenu as searchMenuApi, fetchItemTags, signInWithGoogle, registerUser, loginUser, fetchAuthConfig, fetchSession, startPasswordReset, startEmailVerification } from "../api";

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
  const [userVerified, setUserVerified] = useState(false);
  const [isSavingInfo, setIsSavingInfo] = useState(false);
  const [infoFeedback, setInfoFeedback] = useState(null);
  const [userError, setUserError] = useState(null);
  const [authNotice, setAuthNotice] = useState(null);
  const [authLink, setAuthLink] = useState("");
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [metaById, setMetaById] = useState(new Map());
  const [filters, setFilters] = useState([]);
  // Track which cards are flipped (by item id)
  const [flipped, setFlipped] = useState(() => new Set());
  // Simple gate to prompt the user to start a guest session
  const [showAuthGate, setShowAuthGate] = useState(true);
  const [googleClientId, setGoogleClientId] = useState(process.env.REACT_APP_GOOGLE_CLIENT_ID || "");
  const [googleReady, setGoogleReady] = useState(false);
  const googleBtnRef = React.useRef(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regName, setRegName] = useState("");
  const [regSurname, setRegSurname] = useState("");

  const isFlipped = (id) => flipped.has(id);
  const toggleFlip = (id) => {
    setFlipped(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

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

  // Fetch item metadata (tags/allergens/ingredients) once
  useEffect(() => {
    let mounted = true;
    fetchItemTags()
      .then(data => {
        if (!mounted) return;
        const map = new Map();
        (data.items || []).forEach(item => {
          map.set(item.id, item);
        });
        setMetaById(map);
      })
      .catch(() => {})
    return () => { mounted = false; };
  }, []);

  // Debounced NLP search
  useEffect(() => {
    let timerId;
    setSearchError(null);
    if (!searchQuery || searchQuery.trim().length < 2) {
      setSearchResults([]);
      return undefined;
    }
    setIsSearching(true);
    timerId = setTimeout(() => {
      searchMenuApi(searchQuery.trim(), 8)
        .then(data => {
          setSearchResults(data.results || []);
        })
        .catch(err => setSearchError(err.message || "Errore ricerca"))
        .finally(() => setIsSearching(false));
    }, 300);
    return () => clearTimeout(timerId);
  }, [searchQuery]);

  // On table change, try to reuse a previous guest session for this table in this tab
  useEffect(() => {
    setUserError(null);
    setUserId(null);
    const key = `guest_user_id:${tableId}`;
    const saved = sessionStorage.getItem(key);
    if (saved) {
      const parsed = Number(saved);
      if (!Number.isNaN(parsed)) {
        setUserId(parsed);
        setShowAuthGate(false);
        return;
      }
    }
    // Try to reuse server session cookie
    fetchSession()
      .then(sessUser => {
        if (sessUser && sessUser.id) {
          setUserId(sessUser.id);
          setUserInfo({
            name: sessUser.name || "",
            email: sessUser.email || "",
            phone: sessUser.phone || "",
            age: sessUser.age != null ? String(sessUser.age) : "",
          });
          setUserVerified(Boolean(sessUser.email_verified_at));
          setShowAuthGate(false);
        } else {
          setShowAuthGate(true);
        }
      })
      .catch(() => setShowAuthGate(true));
  }, [tableId]);

  // Heartbeat to detect revoked/expired sessions and prompt re-auth
  useEffect(() => {
    let timerId;
    const revalidate = () => {
      fetchSession()
        .then(sessUser => {
          const valid = !!(sessUser && sessUser.id);
          if (!valid && !showAuthGate) {
            // Clear local references and prompt auth
            setUserId(null);
            setUserInfo({ name: "", email: "", phone: "", age: "" });
            setUserVerified(false);
            setShowAuthGate(true);
          }
        })
        .catch(() => {
          if (!showAuthGate) setShowAuthGate(true);
        });
    };
    // periodic check
    timerId = setInterval(revalidate, 20000);
    // on tab focus
    const onFocus = () => revalidate();
    window.addEventListener('visibilitychange', onFocus);
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(timerId);
      window.removeEventListener('visibilitychange', onFocus);
      window.removeEventListener('focus', onFocus);
    };
  }, [showAuthGate]);

  // Fetch runtime auth configuration if env not present
  useEffect(() => {
    if (googleClientId) return;
    fetchAuthConfig()
      .then(cfg => {
        if (cfg && typeof cfg.google_client_id === 'string') {
          setGoogleClientId(cfg.google_client_id);
        }
      })
      .catch(() => {});
  }, [googleClientId]);

  // Explicit guest session creation
  const handleContinueAsGuest = async () => {
    if (isAuthenticating) return;
    setIsAuthenticating(true);
    setUserError(null);
    try {
      const user = await autoLogin(tableId);
      setUserId(user.id);
      setUserInfo({
        name: user.name || "",
        email: user.email || "",
        phone: user.phone || "",
        age: user.age != null ? String(user.age) : "",
      });
      setUserVerified(Boolean(user.email_verified_at));
      sessionStorage.setItem(`guest_user_id:${tableId}`, String(user.id));
      setShowAuthGate(false);
    } catch (err) {
      setUserError(err.message || "Impossibile avviare la sessione utente.");
    } finally {
      setIsAuthenticating(false);
    }
  };

  // Google Identity Services loader + button rendering
  useEffect(() => {
    if (!showAuthGate) return; // only render on gate
    if (!googleClientId) return; // no client id configured

    const renderButton = () => {
      try {
        if (!window.google || !window.google.accounts || !googleBtnRef.current) return;
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (resp) => {
            const cred = resp && resp.credential;
            if (!cred) return;
            setIsAuthenticating(true);
            setUserError(null);
            try {
              const user = await signInWithGoogle(cred, tableId);
              setUserId(user.id);
              setUserInfo({
                name: user.name || "",
                email: user.email || "",
                phone: user.phone || "",
                age: user.age != null ? String(user.age) : "",
              });
              setUserVerified(Boolean(user.email_verified_at));
              sessionStorage.setItem(`guest_user_id:${tableId}`, String(user.id));
              setShowAuthGate(false);
            } catch (err) {
              setUserError(err.message || "Accesso Google non riuscito.");
            } finally {
              setIsAuthenticating(false);
            }
          },
          auto_select: false,
          cancel_on_tap_outside: true,
          context: "signin",
        });
        const containerWidth = googleBtnRef.current.offsetWidth || 320;
        const bw = Math.min(320, Math.max(200, containerWidth));
        window.google.accounts.id.renderButton(googleBtnRef.current, {
          theme: "outline",
          size: "large",
          width: bw,
          type: "standard",
          shape: "pill",
          text: "signin_with",
          logo_alignment: "left",
        });
        setGoogleReady(true);
      } catch (_) {
        // ignore render failures
      }
    };

    if (window.google && window.google.accounts && window.google.accounts.id) {
      renderButton();
      return;
    }

    const scriptId = "google-identity-services";
    if (document.getElementById(scriptId)) return; // already loading/loaded
    const script = document.createElement("script");
    script.id = scriptId;
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = renderButton;
    document.head.appendChild(script);
  }, [showAuthGate, googleClientId, tableId]);

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    if (isAuthenticating) return;
    setIsAuthenticating(true);
    setUserError(null);
    try {
      const user = await loginUser({ email: loginEmail.trim(), password: loginPassword, tableId });
      setUserId(user.id);
      setUserInfo({
        name: user.name || "",
        email: user.email || "",
        phone: user.phone || "",
        age: user.age != null ? String(user.age) : "",
      });
      setUserVerified(Boolean(user.email_verified_at));
      sessionStorage.setItem(`guest_user_id:${tableId}`, String(user.id));
      setShowAuthGate(false);
    } catch (err) {
      setUserError(err.message || "Accesso non riuscito.");
    } finally {
      setIsAuthenticating(false);
    }
  };

  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    if (isAuthenticating) return;
    setIsAuthenticating(true);
    setUserError(null);
    try {
      const user = await registerUser({ email: regEmail.trim(), password: regPassword, name: regName.trim() || null, surname: regSurname.trim() || null, tableId });
      setUserId(user.id);
      setUserInfo({
        name: user.name || "",
        email: user.email || "",
        phone: user.phone || "",
        age: user.age != null ? String(user.age) : "",
      });
      setUserVerified(Boolean(user.email_verified_at));
      sessionStorage.setItem(`guest_user_id:${tableId}`, String(user.id));
      setShowAuthGate(false);
    } catch (err) {
      setUserError(err.message || "Registrazione non riuscita.");
    } finally {
      setIsAuthenticating(false);
    }
  };

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    if (!loginEmail.trim()) {
      setAuthNotice("Inserisci la tua email sopra e riprova.");
      return;
    }
    try {
      const res = await startPasswordReset(loginEmail.trim());
      setAuthNotice("Se l'email esiste, riceverai un link per reimpostare la password.");
      if (res && res.link) setAuthLink(res.link);
    } catch (err) {
      setAuthNotice("Impossibile inviare l'email di reset al momento.");
    }
  };

  const handleSendVerifyEmail = async () => {
    if (!userInfo.email) return;
    try {
      const res = await startEmailVerification(userInfo.email);
      setAuthNotice("Email di verifica inviata. Controlla la tua casella di posta.");
      if (res && res.link) setAuthLink(res.link);
    } catch (err) {
      setAuthNotice("Impossibile inviare l'email di verifica.");
    }
  };

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

  // Resolve a photo slug for a given item name; used to build JPG and SVG fallback paths
  const getPhotoKey = (name) => {
    if (!name) return "generic";
    const n = String(name).toLowerCase();
    if (n.includes("espresso martini")) return "espresso-martini";
    if (n.includes("negroni")) return "negroni";
    if (n.includes("mojito")) return "mojito";
    if (n.includes("spritz")) return "spritz";
    if (n.includes("vino rosso")) return "wine-red";
    if (n.includes("vino bianco")) return "wine-white";
    if (n.includes("birra")) return "beer";
    if (n.includes("tè freddo") || n.includes("te freddo")) return "iced-tea";
    if (n.includes("acqua frizz")) return "water-sparkling";
    if (n.includes("acqua naturale") || n === "acqua") return "water-still";
    if (n.includes("arancia") || n.includes("succo")) return "orange-juice";
    if (n.includes("americano")) return "americano";
    if (n.includes("macchiato") && n.includes("latte")) return "latte-macchiato";
    if (n.includes("cappuccino")) return "cappuccino";
    if (n.includes("macchiato")) return "espresso-macchiato";
    if (n.includes("espresso")) return "espresso";
    return "generic";
  };
  const buildJpgPath = (key) => `/images/menu/${key}.jpg`;
  const buildSvgPlaceholderPath = (key) => `/icons/${key}.svg`;

  // Filter helpers (AND semantics over selected tags)
  const selectedTags = new Set(filters);
  const resultMatchesFilters = (result) => {
    if (selectedTags.size === 0) return true;
    const tags = Array.isArray(result.tags) ? result.tags : [];
    for (const t of selectedTags) {
      if (!tags.includes(t)) return false;
    }
    return true;
  };

  const itemMatchesFilters = (itemId) => {
    if (selectedTags.size === 0) return true;
    const meta = metaById.get(itemId);
    if (!meta) return false;
    const tags = Array.isArray(meta.tags) ? meta.tags : [];
    for (const t of selectedTags) {
      if (!tags.includes(t)) return false;
    }
    return true;
  };

  const FILTER_OPTIONS = [
    { key: "analcolico", label: "Analcolico" },
    { key: "alcolico", label: "Alcolico" },
    { key: "senza-glutine", label: "Senza glutine" },
    { key: "vegano", label: "Vegano" },
    { key: "vegetariano", label: "Vegetariano" },
    { key: "caffeina", label: "Caffeina" },
    { key: "frizzante", label: "Frizzante" },
    { key: "agrumato", label: "Agrumato" },
  ];

  const toggleFilter = (key) => {
    setFilters(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  };

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
        <div style={{ marginTop: "1rem" }}>
          <input
            type="search"
            placeholder="Cerca (es. agrumato, frizzante, dolce, menta...)"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{
              width: "100%",
              padding: "0.6rem 0.8rem",
              borderRadius: 8,
              border: "1px solid rgba(0,0,0,0.15)",
            }}
          />
          {isSearching && (
            <p className="status-card" style={{ marginTop: "0.5rem" }}>Ricerca in corso...</p>
          )}
          {searchError && (
            <p className="status-card" style={{ marginTop: "0.5rem", color: "#b00020" }}>{searchError}</p>
          )}
        </div>
        <div className="filter-bar">
          {FILTER_OPTIONS.map(opt => (
            <button
              type="button"
              key={opt.key}
              className={`filter-chip ${filters.includes(opt.key) ? "filter-chip--active" : ""}`}
              onClick={() => toggleFilter(opt.key)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </header>
      {userId && userInfo.email && !userVerified && (
        <div className="status-card" style={{ margin: "8px 16px", background: "#fff8e1", border: "1px solid #ffecb3" }}>
          <span style={{ marginRight: 8 }}>Per favore verifica la tua email ({userInfo.email})</span>
          <button type="button" onClick={handleSendVerifyEmail} style={{ padding: "0.35rem 0.6rem", borderRadius: 999, border: "none", background: "#3e2723", color: "#fff", cursor: "pointer" }}>Invia verifica</button>
        </div>
      )}
      <section className="main-content">
        {searchResults.filter(resultMatchesFilters).length > 0 && (
          <section className="menu-category">
            <h2 className="menu-category-title">Risultati ricerca</h2>
            <div className="menu-grid">
              {searchResults.filter(resultMatchesFilters).map(result => (
                <article
                  className={`menu-item flip-card ${isFlipped(result.id) ? "is-flipped" : ""}`}
                  key={`search-${result.id}`}
                  onClick={() => toggleFlip(result.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleFlip(result.id); }}
                >
                  <div className="flip-inner">
                    <div className="flip-front">
                      {(() => {
                        const key = getPhotoKey(result.name);
                        return (
                          <img
                            className="menu-card-image"
                            src={buildJpgPath(key)}
                            alt={result.name}
                            data-key={key}
                            onError={(e) => {
                              const img = e.currentTarget;
                              const k = img.getAttribute('data-key') || 'generic';
                              if (img.getAttribute('data-fallback') === 'svg') {
                                img.onerror = null;
                                img.src = "/icons/generic-drink.svg";
                              } else {
                                img.setAttribute('data-fallback', 'svg');
                                img.src = buildSvgPlaceholderPath(k);
                              }
                            }}
                          />
                        );
                      })()}
                      <div className="menu-card-overlay">
                        <div className="menu-card-title">{result.name}</div>
                      </div>
                    </div>
                    <div className="flip-back">
                      <div className="menu-card-back">
                        <h3 className="menu-card-name">{result.name}</h3>
                        <p className="menu-item-note">Punteggio corrispondenza: {(result.score * 100).toFixed(0)}%</p>
                        {Array.isArray(result.tags) && result.tags.length > 0 && (
                          <div className="tag-list">
                            {result.tags.map(tag => (
                              <span className="tag-badge" key={`${result.id}-tag-${tag}`}>{tag}</span>
                            ))}
                          </div>
                        )}
                        <div className="menu-card-footer">
                          <span className="menu-item-price">€ {formatPrice(result.price)}</span>
                          <button
                            type="button"
                            className="menu-item-add"
                            onClick={(e) => { e.stopPropagation(); handleAddToCart(result); }}
                          >
                            Aggiungi al carrello
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
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

        {categories.map(category => {
          const filteredItems = category.items.filter(item => itemMatchesFilters(item.id));
          if (filteredItems.length === 0) return null;
          return (
          <section className="menu-category" key={category.name}>
            <h2 className="menu-category-title">{category.name}</h2>
            <div className="menu-grid">
              {filteredItems.map(item => (
                <article
                  className={`menu-item flip-card ${isFlipped(item.id) ? "is-flipped" : ""}`}
                  key={item.id}
                  onClick={() => toggleFlip(item.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleFlip(item.id); }}
                >
                  <div className="flip-inner">
                    <div className="flip-front">
                      {(() => {
                        const key = getPhotoKey(item.name);
                        return (
                          <img
                            className="menu-card-image"
                            src={buildJpgPath(key)}
                            alt={item.name}
                            data-key={key}
                            onError={(e) => {
                              const img = e.currentTarget;
                              const k = img.getAttribute('data-key') || 'generic';
                              if (img.getAttribute('data-fallback') === 'svg') {
                                img.onerror = null;
                                img.src = "/icons/generic-drink.svg";
                              } else {
                                img.setAttribute('data-fallback', 'svg');
                                img.src = buildSvgPlaceholderPath(k);
                              }
                            }}
                          />
                        );
                      })()}
                      <div className="menu-card-overlay">
                        <div className="menu-card-title">{item.name}</div>
                      </div>
                    </div>
                    <div className="flip-back">
                      <div className="menu-card-back">
                        <h3 className="menu-card-name">{item.name}</h3>
                        <p className="menu-item-note">
                          {descriptions[item.name] ||
                            "Preparato con ingredienti freschi e selezionati per la tua pausa."}
                        </p>
                        {(() => {
                          const meta = metaById.get(item.id);
                          const tags = meta && Array.isArray(meta.tags) ? meta.tags : [];
                          return tags.length > 0 ? (
                            <div className="tag-list">
                              {tags.map(tag => (
                                <span className="tag-badge" key={`${item.id}-tag-${tag}`}>{tag}</span>
                              ))}
                            </div>
                          ) : null;
                        })()}
                        <div className="menu-card-footer">
                          <span className="menu-item-price">€ {formatPrice(item.price)}</span>
                          <button
                            type="button"
                            className="menu-item-add"
                            onClick={(e) => { e.stopPropagation(); handleAddToCart(item); }}
                          >
                            Aggiungi al carrello
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        );})}

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

      {showAuthGate && (
        <div style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.45)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 1000,
        }}>
          <div style={{
            background: "#fff",
            borderRadius: 14,
            padding: "1.25rem 1.25rem 1rem",
            width: "min(420px, 92vw)",
            boxShadow: "0 16px 36px rgba(0,0,0,0.2)",
            border: "1px solid rgba(0,0,0,0.08)",
            boxSizing: "border-box",
            overflow: "hidden",
          }}>
            <h2 style={{ margin: 0 }}>Benvenuto</h2>
            <p style={{ marginTop: "0.5rem", opacity: 0.9 }}>
              Accedi per personalizzare l&#39;esperienza oppure continua come ospite.
            </p>
            {googleClientId && (
              <div style={{ margin: "0.75rem 0" }}>
                <div ref={googleBtnRef} style={{ display: "flex", justifyContent: "center", width: "100%" }} />
              </div>
            )}
            {userError && (
              <div style={{
                margin: "0.5rem 0 0.75rem",
                padding: "0.5rem 0.75rem",
                borderRadius: 8,
                background: "rgba(229,57,53,0.12)",
                color: "#7d1916",
              }}>
                {userError}
              </div>
            )}
            <div style={{ margin: "0.5rem 0 0.75rem", display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ height: 1, background: "#e5e5e5", flex: 1 }} />
              <div style={{ fontSize: 12, color: "#777" }}>oppure</div>
              <div style={{ height: 1, background: "#e5e5e5", flex: 1 }} />
            </div>
            <h3 style={{ margin: "0 0 0.5rem" }}>Accedi</h3>
            <form onSubmit={handleLoginSubmit} style={{ display: "grid", gap: 8, marginBottom: 12 }}>
              <input type="email" placeholder="Email" value={loginEmail} onChange={e => setLoginEmail(e.target.value)} required style={{ width: "100%", boxSizing: "border-box", padding: "0.55rem 0.6rem", borderRadius: 8, border: "1px solid rgba(0,0,0,0.15)" }} />
              <input type="password" placeholder="Password" value={loginPassword} onChange={e => setLoginPassword(e.target.value)} required style={{ width: "100%", boxSizing: "border-box", padding: "0.55rem 0.6rem", borderRadius: 8, border: "1px solid rgba(0,0,0,0.15)" }} />
              <button type="submit" disabled={isAuthenticating} style={{
                width: "100%", padding: "0.6rem 0.9rem", borderRadius: 999, border: "none",
                background: "#3e2723", color: "#fff", fontWeight: 700, cursor: "pointer"
              }}>Entra</button>
              <div style={{ textAlign: "right" }}>
                <a href="#" onClick={handleForgotPassword} style={{ fontSize: 12, color: "#555", textDecoration: "underline" }}>Password dimenticata?</a>
              </div>
            </form>
            <h3 style={{ margin: "0.5rem 0 0.5rem" }}>Registrati</h3>
            <form onSubmit={handleRegisterSubmit} style={{ display: "grid", gap: 8, marginBottom: 12 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, minWidth: 0 }}>
                <input type="text" placeholder="Nome (opzionale)" value={regName} onChange={e => setRegName(e.target.value)} style={{ width: "100%", boxSizing: "border-box", padding: "0.55rem 0.6rem", borderRadius: 8, border: "1px solid rgba(0,0,0,0.15)" }} />
                <input type="text" placeholder="Cognome (opzionale)" value={regSurname} onChange={e => setRegSurname(e.target.value)} style={{ width: "100%", boxSizing: "border-box", padding: "0.55rem 0.6rem", borderRadius: 8, border: "1px solid rgba(0,0,0,0.15)" }} />
              </div>
              <input type="email" placeholder="Email" value={regEmail} onChange={e => setRegEmail(e.target.value)} required style={{ width: "100%", boxSizing: "border-box", padding: "0.55rem 0.6rem", borderRadius: 8, border: "1px solid rgba(0,0,0,0.15)" }} />
              <input type="password" placeholder="Password (min 8)" value={regPassword} onChange={e => setRegPassword(e.target.value)} required minLength={8} style={{ width: "100%", boxSizing: "border-box", padding: "0.55rem 0.6rem", borderRadius: 8, border: "1px solid rgba(0,0,0,0.15)" }} />
              <button type="submit" disabled={isAuthenticating} style={{
                width: "100%", padding: "0.6rem 0.9rem", borderRadius: 999, border: "none",
                background: "#4e342e", color: "#fff", fontWeight: 700, cursor: "pointer"
              }}>Crea account</button>
            </form>
            {authNotice && (
              <div style={{ marginTop: 8, fontSize: 13, color: "#444" }}>
                {authNotice}
                {authLink && (
                  <>
                    {" "}
                    <a href={authLink} style={{ textDecoration: "underline" }} target="_blank" rel="noreferrer">Apri link</a>
                  </>
                )}
              </div>
            )}
            <button
              type="button"
              onClick={handleContinueAsGuest}
              disabled={isAuthenticating}
              style={{
                width: "100%",
                padding: "0.75rem",
                border: "none",
                borderRadius: 999,
                background: "linear-gradient(135deg, #4e342e, #3e2723)",
                color: "#fff",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              {isAuthenticating ? "Preparazione..." : "Continua come ospite"}
            </button>
            {!googleClientId && (
              <p style={{ marginTop: "0.65rem", fontSize: "0.9rem", opacity: 0.8 }}>
                Suggerimento: configura REACT_APP_GOOGLE_CLIENT_ID per abilitare "Sign in with Google".
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default MenuPage;
