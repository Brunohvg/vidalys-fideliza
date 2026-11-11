import { useEffect, useState } from "react";
import {
  ArrowRight, BadgeCheck, Cable, CircleHelp, CloudDownload, Info,
  Link2, LoaderCircle, LockKeyhole, RefreshCw, ShieldCheck, ShieldX
} from "lucide-react";
import {
  ApiError, merchantApi, type CatalogPreview, type NuvemshopConnectionStatus,
  type Store
} from "./api";

function authUrlValid(raw: string) {
  try {
    const url = new URL(raw);
    return url.origin === "https://www.tiendanube.com" &&
      /^\/apps\/[0-9]+\/authorize$/.test(url.pathname) &&
      Boolean(url.searchParams.get("state"));
  } catch { return false; }
}

export default function NuvemshopConnection({
  tenantId, role, onLivePreview
}: {
  tenantId: string;
  role: Store["role"];
  onLivePreview: (result: CatalogPreview) => void;
}) {
  const canConnect = role === "owner" || role === "admin";
  const [status, setStatus] = useState<NuvemshopConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [reading, setReading] = useState(false);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("nuvemshop");
    if (result === "connected") setNotice("Loja autorizada. A leitura está disponível somente para produtos.");
    if (result === "failed") setError("A autorização não foi concluída. Verifique a conta, sessão e permissões.");
    if (result) {
      params.delete("nuvemshop");
      params.delete("nuvemshop_tenant");
      const remaining = params.toString();
      window.history.replaceState(null, "", window.location.pathname +
        (remaining ? "?" + remaining : "") + window.location.hash);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    setLoading(true); setError("");
    merchantApi.nuvemshopStatus(tenantId).then(value => {
      if (mounted) { setStatus(value); setLoading(false); }
    }).catch(cause => {
      if (mounted) {
        setStatus(null); setLoading(false);
        setError(cause instanceof ApiError ? cause.message : "Conexão com o servidor indisponível.");
      }
    });
    return () => { mounted = false; };
  }, [tenantId, refresh]);

  const connect = async () => {
    if (!canConnect || !status?.configured || starting) return;
    setError(""); setNotice(""); setStarting(true);
    try {
      const started = await merchantApi.beginNuvemshopOAuth(tenantId);
      if (!authUrlValid(started.authorize_url)) {
        throw new Error("O servidor retornou uma URL de autorização inválida.");
      }
      window.location.assign(started.authorize_url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível iniciar a autorização.");
      setStarting(false);
    }
  };

  const preview = async () => {
    if (!status?.connected || reading) return;
    setError(""); setNotice(""); setReading(true);
    try {
      const result = await merchantApi.previewLiveNuvemshop(tenantId, page);
      onLivePreview(result);
      setNotice(result.empty
        ? "Esta página não possui produtos. Nenhum dado foi alterado."
        : "Prévia oficial carregada. Confira abaixo as variantes e custos divergentes.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Falha ao consultar produtos.");
    } finally {
      setReading(false);
    }
  };

  return <section className="nuv-connection" aria-label="Conexão oficial Nuvemshop">
    <div className="nuv-connection-head">
      <div className="nuv-connection-mark"><Cable size={23}/></div>
      <div className="nuv-connection-title">
        <span className="portal-eyebrow">INTEGRAÇÃO OFICIAL</span>
        <h2>Conecte sua Nuvemshop</h2>
        <p>Autorização individual por loja. Apenas leitura de produtos, sem alterações.</p>
      </div>
      <span className={"nuv-connection-pill" + (status?.connected ? " connected" : "")}>
        {loading ? <LoaderCircle size={15}/> : status?.connected ? <BadgeCheck size={15}/> : <ShieldX size={15}/>}
        {loading ? "Verificando" : status?.connected ? "Conectada" : "Não conectada"}
      </span>
    </div>

    <div className="nuv-connection-main">
      <div className="nuv-connection-info">
        <div className="nuv-security-title"><ShieldCheck size={17}/> Suas credenciais ficam protegidas.</div>
        <p>O token é recebido pelo servidor e armazenado criptografado. Não aparece na interface nem no histórico de consultas.</p>
        <div className="nuv-security-facts">
          <span><LockKeyhole size={15}/> Sem acesso a pedidos</span>
          <span><ShieldCheck size={15}/> Sem permissão de edição</span>
          <span><Link2 size={15}/> Vínculo exclusivo à loja</span>
        </div>
        {status?.connected && <div className="nuv-store-identity">
          <span>Loja conectada <b>#{status.store_id}</b></span>
          <span>Permissão <b>{status.scope}</b></span>
        </div>}
        {status && !status.configured && <div className="nuv-setup-note">
          <Info size={17}/> Integração ainda não configurada no servidor de homologação. É necessário cadastrar o aplicativo e as variáveis seguras no Coolify.
        </div>}
      </div>

      <div className="nuv-connection-actions">
        {status?.connected ? <>
          <div className="nuv-action-label"><CloudDownload size={17}/> Prévia real sem gravação</div>
          <label htmlFor="nuv-preview-page">Página do catálogo</label>
          <div className="nuv-preview-tools">
            <input id="nuv-preview-page" type="number" min={1} max={10000}
              value={page} onChange={e => setPage(Number(e.target.value))}
              aria-label="Página do catálogo Nuvemshop"/>
            <button className="portal-primary" disabled={reading || !Number.isInteger(page) || page < 1 || page > 10000}
              onClick={preview}>
              {reading ? <LoaderCircle size={17} className="reconcile-spin"/> : <CloudDownload size={17}/>}
              {reading ? "Consultando…" : "Consultar 3 produtos"}
            </button>
          </div>
          <small>Consulta diretamente na API oficial; nenhum item é importado automaticamente.</small>
        </> : <>
          <div className="nuv-action-label"><CircleHelp size={17}/> Como funciona?</div>
          <p>A Nuvemshop solicitará sua aprovação para ler os produtos. Depois você voltará ao Fideliza.</p>
          <button className="portal-primary" type="button" disabled={!canConnect || !status?.configured || starting}
            onClick={connect}>
            {starting ? <LoaderCircle className="reconcile-spin" size={17}/> : <Link2 size={17}/>}
            {starting ? "Iniciando…" : "Autorizar minha loja"} <ArrowRight size={17}/>
          </button>
          {!canConnect && <small>Somente proprietário ou administrador pode autorizar uma loja.</small>}
          {!status?.configured && <small>Disponível após configurar as credenciais da aplicação no Coolify.</small>}
        </>}
        <button className="nuv-refresh" onClick={() => setRefresh(n => n + 1)}
          disabled={loading || starting || reading}><RefreshCw size={15}/> Atualizar status</button>
      </div>
    </div>
    {notice && <div className="nuv-notice" role="status"><BadgeCheck size={16}/>{notice}</div>}
    {error && <div className="reconcile-error" role="alert"><Info size={16}/>{error}</div>}
  </section>;
}
