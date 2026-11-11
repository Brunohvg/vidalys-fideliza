import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Portal from "./Portal";
import PublicEnrollment from "./PublicEnrollment";
import "./styles.css";
import "./portal.css";
import "./fideliza-theme.css";

// A demo nunca usa credenciais, dados ou endpoints de lojistas.
// A rota principal exige sessão real do Django.
const isDemo = window.location.pathname === "/demo";
const isEnrollment = window.location.pathname === "/participar";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {isEnrollment ? <PublicEnrollment /> : isDemo ? <App /> : <Portal />}
  </React.StrictMode>
);
