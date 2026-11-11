import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight, BadgeCheck, ChevronLeft, ChevronRight, CircleHelp,
  HeartHandshake, LockKeyhole, RefreshCw, Search, ShieldCheck,
  UserRoundCheck, UsersRound
} from "lucide-react";
import {
  ApiError, merchantApi, type ParticipantDirectoryResponse,
  type ProgramParticipant
} from "./api";

function dateString(value: string | null) {
  if (!value) return "Não disponível";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Não disponível" :
    parsed.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

function displayName(item: ProgramParticipant) {
  return item.display_name || "Participante sem nome informado";
}

export default function ParticipantsBoard({ tenantId }: { tenantId: string }) {
  const [response, setResponse] = useState<ParticipantDirectoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"all"|"active"|"paused">("all");
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);

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
    <section className="xp-hero">
      <div>
        <span className="xp-eyebrow"><HeartHandshake size={16}/> RELACIONAMENTO COM CLIENTES</span>
        <h2>Clientes que voltam.<br/><em>Relacionamentos que crescem.</em></h2>
        <p>Acompanhe quem aderiu ao programa de fidelidade, com consentimento verificável e informações separadas das vendas comuns da loja.</p>
        <span className="xp-hero-note"><LockKeyhole size={15}/> Nenhum cliente entra no programa automaticamente.</span>
      </div>
      <div className="xp-hero-graphic" aria-hidden="true"><UsersRound size={66} strokeWidth={1.3}/></div>
    </section>

    <div className="xp-stats">
      <div className="xp-stat"><span><UsersRound size={17}/> Participantes</span><strong>{response?.summary.total ?? "—"}</strong><small>Com cadastro de adesão</small></div>
      <div className="xp-stat"><span><BadgeCheck size={17}/> Participando</span><strong>{response?.summary.active ?? "—"}</strong><small>Adesão ativa</small></div>
      <div className="xp-stat"><span><CircleHelp size={17}/> Pausados</span><strong>{response?.summary.paused ?? "—"}</strong><small>Sem recompensa ativa</small></div>
      <div className="xp-stat"><span><ShieldCheck size={17}/> Saldo de benefícios</span><strong className="xp-pending-value">Ainda não disponível</strong><small>Depende da carteira e do ledger</small></div>
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
            ?"A área está pronta, mas ainda não existe um canal de adesão publicado. Conectar a Nuvemshop não transforma compradores em participantes."
            :"Ajuste a busca ou o filtro para encontrar outros participantes."}</p>
          {response.summary.total===0 && <div className="xp-empty-steps">
            <span><BadgeCheck size={16}/> Definir as regras do programa</span>
            <span><BadgeCheck size={16}/> Criar o aceite na vitrine</span>
            <span><BadgeCheck size={16}/> Registrar adesões autorizadas</span>
          </div>}
        </div> : !error && response &&
        <div className="xp-table-wrap">
          <table className="xp-table"><thead><tr><th>Cliente participante</th><th>Adesão</th><th>Situação</th><th>Saldo / atividade</th></tr></thead>
          <tbody>{response.items.map(item=><tr key={item.id}>
            <td><div className="xp-person"><span className="xp-person-avatar">{displayName(item).slice(0,1).toUpperCase()}</span>
              <span><strong>{displayName(item)}</strong><small>{item.contact_email || "Contato não informado"}</small></span></div></td>
            <td><strong>{dateString(item.consented_at)}</strong><small>{item.consent_channel==="customer_portal"?"Portal do participante":"Aceite na loja"}</small></td>
            <td><span className={"xp-tag "+item.status}>{item.status==="active"?"Participando":"Pausado"}</span></td>
            <td><span className="xp-unavailable">Aguardando carteira</span><small>Atividade: {dateString(item.last_program_activity_at)}</small></td>
          </tr>)}</tbody></table>
        </div>}
      {!loading && !error && response && response.total_filtered>0 && <div className="xp-pagination">
        <span>{response.total_filtered} participante(s) encontrado(s)</span>
        <div><button aria-label="Página anterior" disabled={offset===0} onClick={()=>setOffset(n=>Math.max(0,n-20))}><ChevronLeft size={18}/></button>
          <span>{Math.floor(offset/20)+1}</span>
          <button aria-label="Próxima página" disabled={offset+20>=response.total_filtered} onClick={()=>setOffset(n=>n+20)}><ChevronRight size={18}/></button></div>
      </div>}
    </section>

    <aside className="xp-guidance"><ShieldCheck size={19}/><div><strong>Privacidade antes de campanhas.</strong>
      <p>Adesão, contato de marketing e compartilhamento de dados têm finalidades distintas. O Fideliza exigirá um aceite verificável antes de atribuir benefícios; clientes sem aceite não aparecerão nesta lista.</p></div>
      <ArrowRight size={18} className="xp-guidance-arrow"/></aside>
  </div>;
}
