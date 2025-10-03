import React from "react";
import { Link } from "react-router-dom";

function HomePage() {
  return (
    <>
      <header>
        <h1>Bar Nipo</h1>
        <p style={{ marginTop: "0.5rem", opacity: 0.85 }}>
          Aroma intenso, servizio digitale.
        </p>
      </header>

      <section className="main-content">
        <div className="highlight-card">
          <span className="badge">Live</span>
          <h2>Benvenuto nel menu digitale</h2>
          <p>
            Condividi il QR code con i tuoi clienti e lascia che scoprano il menu
            del bar direttamente dal proprio smartphone. Nessun download, solo
            un&apos;esperienza elegante e veloce.
          </p>
          <p>
            Per provare subito, apri un menu di esempio:
            <br />
            <Link to="/table/sample">Menu tavolo di prova</Link>
          </p>
        </div>
      </section>

      <footer>
        © {new Date().getFullYear()} Bar Nipo · Powered by QR Bar Platform
      </footer>
    </>
  );
}

export default HomePage;
