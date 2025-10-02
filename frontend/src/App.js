import React from "react";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import MenuPage from "./pages/MenuPage";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/table/:tableId" element={<MenuPage />} />
      </Routes>
    </Router>
  );
}

export default App;
