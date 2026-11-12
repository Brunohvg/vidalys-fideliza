import { useEffect, useState } from "react";
import {
  BadgeCheck, Cable, CloudDownload, Info, LoaderCircle,
  RefreshCw, Settings2, ShieldCheck, ShieldX
} from "lucide-react";
import {
  ApiError, merchantApi, type CatalogPreview, type NuvemshopConnectionStatus,
  type Store
} from "./api";

/** A autorização OAuth é administrada exclusivamente em Configurações. */
export default function NuvemshopConnection({
  tenantId, onLivePreview, onOpenSettings
}: {
  tenantId: string;
  role: Store["role"];
  onLivePreview: (result: CatalogPreview) => void;
  onOpenSettings: () => void;
}) {
  const [status, setStatus] = useState<NuvemshopConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [reading, setReading] = useState(false);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let mounted = true;
    setLoading(true); setError(""); setNotice(""); setStatus(null);
    merchantApi.nuvemshopStatus(tenantId).then(value => {
      if (mounted) { setStatus(value); setLoading(false); }
    }).catch(cause => {
      if (mounted) {
        setStatus(null); setLoading(false);
        setError(cause instanceof ApiError
          ? "Não foi possível consultar a situação da sua loja."
          : "Conexão com o servidor indisponível.");
      }
    });
    return () => { mounted = false; };
  }, [tenantId, refresh]);

  const preview = async () => {
    if (!status?.connected || status.connection_check?.catalog_scope_granted===false || reading) return;
    setError(""); setNotice(""); setReading(true);
    try {
      const result = await merchantApi.previewLiveNuvemshop(tenantId, page);
      onLivePreview(result);
      setNotice(result.empty
        ? "Esta página não possui produtos. Nenhum dado foi alterado."
        : "Prévia oficial carregada. Confira abaixo as variantes e custos divergentes.");
    } catch (cause) {
      setError(cause instanceof ApiError
        ? "Não foi possível consultar o catálogo. Confira a conexão em Configurações."
        : "Falha ao consultar produtos.");
    } finally {
      setReading(false);
    }
  };

  return <section className="nuv-connection" aria-label="Consulta de catálogo Nuvemshop">
    <div className="nuv-connection-head">
      <div className="nuv-connection-mark"><Cable size={23}/></div>
      <div className="nuv-connection-title">
        <span className="portal-eyebrow">CATÁLOGO DA LOJA</span>
        <h2>Consulte produtos da sua Nuvemshop</h2>
        <p>A conexão é gerenciada em Configurações. Aqui você apenas confere produtos, sem alterar a loja.</p>
      </div>
      <span className={"nuv-connection-pill" + (status?.connected ? " connected" : "")}>
        {loading ? <LoaderCircle size={15}/> : status?.connected ? <BadgeCheck size={15}/> : <ShieldX size={15}/>}
        {loading ? "Verificando" : status?.connected ? "Autorizada" : "Não vinculada"}
      </span>
    </div>
    <div className="nuv-connection-main">
      <div className="nuv-connection-info">
        <div className="nuv-security-title"><ShieldCheck size={17}/> Consulta protegida e somente leitura.</div>
        <p>Amostras do catálogo são conferidas sem importar variantes, alterar preços ou registrar recompensas.</p>
        {status?.connected&&<p>A autorização foi registrada, mas a validade atual do acesso só é comprovada quando a consulta real à Nuvemshop funcionar.</p>}
        {status?.connection_check?.next_step==="grant_read_products_and_reinstall"&&<p>
          Falta permissão para consultar produtos. Atualize o escopo no Portal de Parceiros e reinstale o aplicativo.
        </p>}
        {!loading && !status?.connected && <p>
          Para consultar seus produtos, abra Configurações e confira a conexão da loja.
        </p>}
      </div>
      <div className="nuv-connection-actions">
        {status?.connected && status.connection_check?.catalog_scope_granted!==false ? <>
          <div className="nuv-action-label"><CloudDownload size={17}/> Prévia real sem gravação</div>
          <label htmlFor="nuv-preview-page">Página do catálogo</label>
          <div className="nuv-preview-tools">
            <input id="nuv-preview-page" type="number" min={1} max={10000}
              value={page} onChange={e => setPage(Number(e.target.value))}
              aria-label="Página do catálogo Nuvemshop"/>
            <button className="portal-primary" type="button"
              disabled={reading || !Number.isInteger(page) || page < 1 || page > 10000}
              onClick={preview}>
              {reading ? <LoaderCircle size={17} className="reconcile-spin"/> : <CloudDownload size={17}/>}
              {reading ? "Consultando…" : "Consultar 3 produtos"}
            </button>
          </div>
          <small>Consulta à loja autorizada. Nenhum dado é importado automaticamente.</small>
        </> : <div className="nuv-action-label">
          <Info size={17}/> A leitura de produtos depende da conexão da loja.
        </div>}
        <button className="nuv-refresh" type="button" onClick={onOpenSettings}>
          <Settings2 size={15}/> Ver conexão em Configurações
        </button>
        <button className="nuv-refresh" type="button" onClick={() => setRefresh(n => n + 1)}
          disabled={loading || reading}><RefreshCw size={15}/> Atualizar status</button>
      </div>
    </div>
    {notice && <div className="nuv-notice" role="status"><BadgeCheck size={16}/>{notice}</div>}
    {error && <div className="reconcile-error" role="alert"><Info size={16}/>{error}</div>}
  </section>;
}
