import React from "react";
import { Link } from "react-router-dom";

function HomePage() {
  return (
    <main style={{ padding: "2rem", fontFamily: "sans-serif", textAlign: "center" }}>
      <h1>QR Bar Frontend</h1>
      <p>The React app is running correctly.</p>
      <p>Scan a table QR code or visit a menu directly to see the live data.</p>
      <p>
        Example:&nbsp;
        <Link to="/table/sample">Open sample table menu</Link>
      </p>
    </main>
  );
}

export default HomePage;
