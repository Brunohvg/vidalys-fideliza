import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Portal from "./Portal";
import MerchantLinkLanding from "./MerchantLinkLanding";
import PublicEnrollment from "./PublicEnrollment";
import MemberClub from "./MemberClub";
import EmailAction from "./EmailAction";
import WithdrawalRequest from "./WithdrawalRequest";
import {entryRoute} from "./routes";
import "./styles.css";
import "./portal.css";
import "./fideliza-theme.css";
import "./experience.css";

const entry = entryRoute(window.location.pathname);
const content = (() => {
  switch (entry) {
    case "email-action": return <EmailAction />;
    case "withdrawal": return <WithdrawalRequest />;
    case "enrollment": return <PublicEnrollment />;
    case "demo": return <App />;
    case "member": return <MemberClub />;
    case "merchant-auth": return <MerchantLinkLanding />;
    case "merchant": return <Portal />;
    default: return <main className="route-not-found">
      <h1>Página não encontrada</h1>
      <p>Confira o endereço ou retorne ao painel.</p>
      <a href="/app/visao-geral">Ir para o painel</a>
    </main>;
  }
})();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{content}</React.StrictMode>
);
