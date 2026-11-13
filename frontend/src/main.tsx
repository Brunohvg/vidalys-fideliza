import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Portal from "./Portal";
import MerchantLinkLanding from "./MerchantLinkLanding";
import PublicEnrollment from "./PublicEnrollment";
import MemberClub from "./MemberClub";
import EmailAction from "./EmailAction";
import WithdrawalRequest from "./WithdrawalRequest";
import "./styles.css";
import "./portal.css";
import "./fideliza-theme.css";

// A demo nunca usa credenciais, dados ou endpoints de lojistas.
// A rota principal exige sessão real do Django.
const isDemo = window.location.pathname === "/demo";
const isMemberClub = /^\/clube\/[a-z0-9-]+\/?$/i.test(window.location.pathname);
const isMerchantEmailLink = ["/confirmar-conta", "/redefinir-senha"]
  .includes(window.location.pathname.replace(/\/+$/, ""));
const isEmailAction = window.location.pathname === "/confirmar";
const isWithdrawal = /^\/retirar\/[a-z0-9-]+\/?$/i.test(window.location.pathname);
const isEnrollment = window.location.pathname === "/participar" ||
  /^\/participar\/[a-z0-9-]+\/?$/i.test(window.location.pathname);
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {isEmailAction ? <EmailAction /> : isWithdrawal ? <WithdrawalRequest /> : isEnrollment ? <PublicEnrollment /> : isDemo ? <App /> : isMemberClub ? <MemberClub /> : isMerchantEmailLink ? <MerchantLinkLanding /> : <Portal />}
  </React.StrictMode>
);
