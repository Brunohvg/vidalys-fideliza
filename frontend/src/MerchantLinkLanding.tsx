import { useEffect, useState } from "react";
import MerchantAccess from "./MerchantAccess";
import { ApiError, merchantApi } from "./api";

/**
 * Rota independente para links de e-mail do lojista.
 *
 * Uma sessão já autenticada NUNCA pode ocultar a confirmação recebida.
 * Somente o POST com token válido substitui a sessão Django.
 * Esta página não carrega componentes/consultas da loja anterior.
 */
export default function MerchantLinkLanding() {
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    let mounted = true;
    merchantApi.getSession().then(session => {
      if (mounted) setActiveAccount(session.authenticated ? session.user.display_name : null);
    }).catch(() => {
      // Falha em consultar sessão não impede abrir um link válido de confirmação.
      if (mounted) setActiveAccount(null);
    });
    return () => { mounted = false; };
  }, []);

  const onVerified = async () => {
    const session = await merchantApi.getSession();
    if (!session.authenticated || session.tenants.length === 0) {
      throw new Error("Conta confirmada, mas a empresa não está disponível. Contate o suporte.");
    }
    // Recarrega a raiz com a nova sessão, evitando estado visual da loja anterior.
    window.location.replace("/");
  };

  const onLogin = async (email: string, password: string) => {
    setBusy(true); setAuthError("");
    try {
      await merchantApi.login(email, password);
      window.location.replace("/");
    } catch (error) {
      setAuthError(error instanceof ApiError
        ? error.message : "Não foi possível entrar. Verifique sua conexão.");
    } finally {
      setBusy(false);
    }
  };

  const onSwitchAccount = async () => {
    await merchantApi.logout();
    setActiveAccount(null);
    setAuthError("");
  };

  const onNavigate = (path: string) => {
    if (path === "/" && activeAccount) {
      // "Voltar à conta conectada" é diferente de "Ir ao login".
      window.location.replace("/");
    }
  };

  return <MerchantAccess
    onLogin={onLogin}
    onVerified={onVerified}
    onSwitchAccount={onSwitchAccount}
    onNavigate={onNavigate}
    activeAccount={activeAccount}
    busy={busy}
    authError={authError}
  />;
}
