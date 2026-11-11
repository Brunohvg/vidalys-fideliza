import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Portal from "./Portal";
import PublicEnrollment from "./PublicEnrollment";
import EmailAction from "./EmailAction";
import WithdrawalRequest from "./WithdrawalRequest";
import "./styles.css";
import "./portal.css";
import "./fideliza-theme.css";

// A demo nunca usa credenciais, dados ou endpoints de lojistas.
// A rota principal exige sessão real do Django.
const isDemo = window.location.pathname === "/demo";
const isEmailAction = window.location.pathname === "/confirmar";
const isWithdrawal = /^\/retirar\/[a-z0-9-]+\/?$/i.test(window.location.pathname);
const isEnrollment = window.location.pathname === "/participar" ||
  /^\/participar\/[a-z0-9-]+\/?$/i.test(window.location.pathname);
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {isEmailAction ? <EmailAction /> : isWithdrawal ? <WithdrawalRequest /> : isEnrollment ? <PublicEnrollment /> : isDemo ? <App /> : <Portal />}
  </React.StrictMode>
);
