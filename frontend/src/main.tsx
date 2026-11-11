import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Portal from "./Portal";
import "./styles.css";
import "./portal.css";

// A demo nunca usa credenciais, dados ou endpoints de lojistas.
// A rota principal exige sessão real do Django.
const isDemo = window.location.pathname === "/demo";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {isDemo ? <App /> : <Portal />}
  </React.StrictMode>
);
