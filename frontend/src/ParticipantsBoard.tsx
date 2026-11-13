import "./wallet-details.css";
import "./program-hub.css";
import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight, BadgeCheck, ChevronLeft, ChevronRight, CircleHelp,
  HeartHandshake, RefreshCw, Search, ShieldCheck,
  UserRoundCheck, UsersRound
} from "lucide-react";
import {
  ApiError, merchantApi, type CashbackWalletView, type ParticipantDirectoryResponse,
  type ProgramParticipant
} from "./api";

const money = (value: number) => new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL"
}).format(value / 100);

const movements: Record<CashbackWalletView["events"][number]["kind"], string> = {
  accrual:"Crédito pendente", release:"Liberação interna", reserve:"Reserva interna",
  cancel_reservation:"Reserva cancelada", redeem:"Resgate registrado",
  expire:"Crédito expirado", reverse_pending:"Estorno pendente",
  reverse_available:"Estorno de saldo liberado"
};

function dateString(value: string | null) {
  if (!value) return "Não disponível";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Não disponível" :
    parsed.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

function displayName(item: ProgramParticipant) {
  return item.display_name || "Participante sem nome informado";
}

export default function ParticipantsBoard({ tenantId, onOpenProgram }: { tenantId: string; onOpenProgram: () => void }) {
  const [response, setResponse] = useState<ParticipantDirectoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"all"|"active"|"paused">("all");
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<ProgramParticipant | null>(null);
  const [wallet, setWallet] = useState<CashbackWalletView | null>(null);
  const [walletLoading, setWalletLoading] = useState(false);
  const [walletError, setWalletError] = useState("");

  const openWallet = async (item: ProgramParticipant) => {
    setSelected(item); setWallet(null); setWalletError(""); setWalletLoading(true);
    try {
      const result = await merchantApi.participantWallet(tenantId, item.id);
      setWallet(result);
    } catch (cause) {
      setWalletError(cause instanceof ApiError ? cause.message : "Falha ao consultar extrato.");
    } finally {
      setWalletLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    merchantApi.listParticipants(tenantId, {q:search,status,offset}).then(result => {
      if (active) {setResponse(result);setLoading(false);}
    }).catch(cause => {
      if (active) {
        setError(cause instanceof ApiError ? cause.message : "Falha ao carregar participantes.");
        setLoading(false);
      }
    });
    return () => {active=false;};
  }, [tenantId,search,status,offset,version]);

  const submit = (e:FormEvent) => {e.preventDefault();setOffset(0);setSearch(searchText.trim());};

  return <div className="experience-page">
    <section className="vf-clients-banner">
      <div><span className="portal-eyebrow">BASE DO CLUBE</span>
        <h2>Quem faz parte do seu programa</h2>
        <p>Esta lista contém participantes verificados. Quem apenas comprou na loja não é inscrito automaticamente.</p>
      </div>
      <button type="button" className="vf-program-outline" onClick={onOpenProgram}>
        <HeartHandshake size={17}/> Gerenciar adesões <ArrowRight size={16}/>
      </button>
    </section>

    <div className="xp-stats">
      <div className="xp-stat"><span><UsersRound size={17}/> Participantes</span><strong>{response?.summary.total ?? "—"}</strong><small>Com cadastro de adesão</small></div>
      <div className="xp-stat"><span><BadgeCheck size={17}/> Participando</span><strong>{response?.summary.active ?? "—"}</strong><small>Adesão ativa</small></div>
      <div className="xp-stat"><span><CircleHelp size={17}/> Pausados</span><strong>{response?.summary.paused ?? "—"}</strong><small>Sem recompensa ativa</small></div>
      <div className="xp-stat"><span><ShieldCheck size={17}/> Pontos e recompensas</span><strong className="xp-pending-value">Não ativados</strong><small>Sem pontuação automática nesta fase</small></div>
    </div>

    <section className="xp-panel">
      <div className="xp-panel-title">
        <div><span className="portal-eyebrow">SEU PROGRAMA DE FIDELIDADE</span><h2>Participantes</h2>
          <p>Somente clientes que aceitaram participar do programa.</p></div>
        <button className="xp-link-btn" type="button" disabled={loading} onClick={()=>setVersion(n=>n+1)}>
          <RefreshCw size={17}/> Atualizar
        </button>
      </div>

      <div className="xp-toolbar">
        <form onSubmit={submit} className="xp-search"><Search size={17}/>
          <input value={searchText} maxLength={80} aria-label="Buscar participantes"
            onChange={e=>setSearchText(e.target.value)}
            placeholder="Buscar nome, e-mail ou referência"/>
          <button type="submit">Buscar</button>
        </form>
        <label className="xp-filter">Situação
          <select aria-label="Filtrar participantes" value={status}
            onChange={e=>{setStatus(e.target.value as typeof status);setOffset(0);}}>
            <option value="all">Todos</option><option value="active">Participando</option><option value="paused">Pausados</option>
          </select>
        </label>
      </div>
      {error && <div className="xp-error" role="alert">{error}
        <button type="button" onClick={()=>setVersion(n=>n+1)}>Tentar novamente</button></div>}
      {loading ? <div className="xp-loading" role="status">Carregando participantes…</div> :
      !error && response && response.items.length===0 ?
        <div className="xp-empty">
          <div className="xp-empty-icon"><UserRoundCheck size={39}/></div>
          <h3>{response.summary.total===0?"Sua comunidade começa com o primeiro aceite":"Nenhum participante encontrado"}</h3>
          <p>{response.summary.total===0
            ?"Os convites de adesão entram primeiro na fila de verificação. Conectar a Nuvemshop não transforma compradores em participantes."
            :"Ajuste a busca ou o filtro para encontrar outros participantes."}</p>
          {response.summary.total===0 && <div className="xp-empty-steps">
            <span><BadgeCheck size={16}/> Aprovar o regulamento</span>
            <span><BadgeCheck size={16}/> Compartilhar a página do clube</span>
            <span><BadgeCheck size={16}/> Confirmar adesões</span>
          </div>}
        </div> : !error && response &&
        <div className="xp-table-wrap">
          <table className="xp-table"><thead><tr><th>Cliente participante</th><th>Adesão</th><th>Situação</th><th>Benefícios / atividade</th></tr></thead>
          <tbody>{response.items.map(item=><tr key={item.id}>
            <td><div className="xp-person"><span className="xp-person-avatar">{displayName(item).slice(0,1).toUpperCase()}</span>
              <span><strong>{displayName(item)}</strong><small>{item.contact_email || "Contato não informado"}</small></span></div></td>
            <td><strong>{dateString(item.consented_at)}</strong><small>{item.consent_channel==="customer_portal"?"Portal do participante":"Aceite na loja"}</small></td>
            <td><span className={"xp-tag "+item.status}>{item.status==="active"?"Participando":"Pausado"}</span></td>
            <td><span className="xp-unavailable">Pontos ainda não ativados</span>
              <small>Atividade: {dateString(item.last_program_activity_at)}</small>
              {item.balance_status === "ledger_only" && item.cashback_balance_cents !== null &&
                <details className="vf-wallet-technical">
                  <summary>Registros internos de teste</summary>
                  <p>Este ledger em reais não representa pontos nem benefício disponível.</p>
                  <button type="button" className="vf-wallet-open" onClick={() => void openWallet(item)}>
                    Ver extrato técnico
                  </button>
                </details>}
            </td>
          </tr>)}</tbody></table>
        </div>}
      {!loading && !error && response && response.total_filtered>0 && <div className="xp-pagination">
        <span>{response.total_filtered} participante(s) encontrado(s)</span>
        <div><button aria-label="Página anterior" disabled={offset===0} onClick={()=>setOffset(n=>Math.max(0,n-20))}><ChevronLeft size={18}/></button>
          <span>{Math.floor(offset/20)+1}</span>
          <button aria-label="Próxima página" disabled={offset+20>=response.total_filtered} onClick={()=>setOffset(n=>n+20)}><ChevronRight size={18}/></button></div>
      </div>}
    </section>

    {selected && <section className="xp-panel vf-wallet-detail" aria-label="Extrato interno do participante">
      <div className="vf-wallet-heading">
        <div><span className="portal-eyebrow">CARTEIRA EM HOMOLOGAÇÃO</span>
          <h3>Histórico de {displayName(selected)}</h3>
          <p>Dados contábeis em reais, exclusivos para verificação interna. Não representam pontos e não permitem resgate.</p>
        </div>
        <button type="button" className="vf-wallet-close"
          onClick={() => {setSelected(null);setWallet(null);setWalletError("");}}>Fechar</button>
      </div>
      {walletLoading && <p role="status">Carregando extrato…</p>}
      {walletError && <p role="alert" className="vf-wallet-error">{walletError}</p>}
      {!walletLoading && wallet?.balances && <>
        <div className="vf-wallet-balances">
          <div><span>Disponível no ledger</span><strong>{money(wallet.balances.available_cents)}</strong></div>
          <div><span>Pendente</span><strong>{money(wallet.balances.pending_cents)}</strong></div>
          <div><span>Reservado</span><strong>{money(wallet.balances.reserved_cents)}</strong></div>
        </div>
        <p className="vf-wallet-disclaimer">Resgate desativado. Movimentações somente de teste
          até que pagamentos e regras sejam validados.</p>
        <h4>Últimas movimentações</h4>
        {wallet.events.length ? <ul className="vf-wallet-events">
          {wallet.events.map(entry => <li key={entry.id}>
            <span><strong>{movements[entry.kind]}</strong>
              <small>{dateString(entry.created_at)} · Regra {entry.rule_version}</small></span>
            <strong>{money(entry.amount_cents)}</strong>
          </li>)}
        </ul> : <p>Nenhuma movimentação registrada.</p>}
      </>}
      {!walletLoading && wallet && !wallet.balances &&
        <p>Carteira ainda não disponível para este participante.</p>}
    </section>}
    
    <aside className="xp-guidance"><ShieldCheck size={19}/><div><strong>Privacidade antes de campanhas.</strong>
      <p>Adesão, contato de marketing e compartilhamento de dados têm finalidades distintas. O Fideliza exigirá um aceite verificável antes de atribuir benefícios; clientes sem aceite não aparecerão nesta lista.</p></div>
      <ArrowRight size={18} className="xp-guidance-arrow"/></aside>
  </div>;
}
