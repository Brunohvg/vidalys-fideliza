import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertTriangle, ArrowRight, BadgeCheck, Calculator, ChevronDown,
  ChevronLeft, CircleDollarSign, Gift, LockKeyhole, ShieldCheck,
  RefreshCw, Save, Sparkles, Target, UsersRound
} from "lucide-react";
import CampaignPlanner from "./CampaignPlanner";
import "./campaign-drafts.css";
import RewardPreview from "./RewardPreview";
import BenefitScenario from "./BenefitScenario";
import { brl, parseBrl, parsePercent } from "./finance";
import { ApiError, merchantApi, type CampaignDraft, type CampaignDraftInput, type Store } from "./api";

type Goal = "second_purchase" | "reactivation" | "recurrence";
const goals: {id:Goal;title:string;description:string;icon:typeof Gift;label:string}[] = [
  {id:"second_purchase",title:"Incentivar a segunda compra",
    description:"Ajudar quem acabou de comprar a ter motivo para voltar.",
    icon:Gift,label:"Segunda compra"},
  {id:"reactivation",title:"Reconquistar participantes",
    description:"Planejar um benefício para quem está há mais tempo sem comprar.",
    icon:UsersRound,label:"Reativação"},
  {id:"recurrence",title:"Estimular compras recorrentes",
    description:"Valorizar clientes que compram com regularidade.",
    icon:Target,label:"Recorrência"}
];

type Preview = {
  ticket:number;
  orders:number;
  rate:number;
  budget:number;
  creditPerOrder:number;
  totalExposure:number;
  remaining:number;
  exceed:boolean;
  capacity:number;
};

function parsePreview(ticket:string, orders:string, cashback:string, budget:string):Preview {
  const t=parseBrl(ticket);
  const b=parseBrl(budget);
  const rate=parsePercent(cashback);
  if (t===null || b===null || t<=0 || b<=0) throw new Error("Informe ticket médio e orçamento maiores que zero.");
  if (rate<1 || rate>1000) throw new Error("Nesta etapa, escolha um benefício de 0,01% até 10%.");
  if (!/^\d{1,5}$/.test(orders.trim())) throw new Error("Informe uma quantidade inteira de até 50.000 pedidos.");
  const n=Number(orders.trim());
  if (!Number.isInteger(n)||n<1||n>50000) throw new Error("Informe de 1 a 50.000 pedidos.");
  const per=Math.floor((t*rate+5000)/10000);
  if (per<=0) throw new Error("A taxa gera crédito inferior a um centavo por compra.");
  const exposure=per*n;
  return {ticket:t,budget:b,orders:n,rate,creditPerOrder:per,
    totalExposure:exposure,remaining:Math.max(0,b-exposure),exceed:exposure>b,
    capacity:Math.floor(b/per)};
}

export default function CampaignGuide({tenantId, role}:{tenantId:string;role:Store["role"]}) {
  const [goal,setGoal]=useState<Goal>("second_purchase");
  const [ticket,setTicket]=useState("");
  const [orders,setOrders]=useState("");
  const [cashback,setCashback]=useState("2");
  const [budget,setBudget]=useState("");
  const [step,setStep]=useState<1|2|3>(1);
  const [error,setError]=useState("");
  const [result,setResult]=useState<Preview|null>(null);
  const [showAdvanced,setShowAdvanced]=useState(false);
  const [drafts,setDrafts]=useState<CampaignDraft[]>([]);
  const [draftLoading,setDraftLoading]=useState(true);
  const [draftListError,setDraftListError]=useState("");
  const [selectedDraft,setSelectedDraft]=useState<CampaignDraft|null>(null);
  const [saving,setSaving]=useState(false);
  const [saveNotice,setSaveNotice]=useState("");
  const [saveError,setSaveError]=useState("");
  const canSave=role==="owner"||role==="admin";

  useEffect(()=>{
    let active=true;
    setDraftLoading(true);
    merchantApi.listCampaignDrafts(tenantId).then(response=>{
      if(active){setDrafts(response.items);setDraftListError("");setDraftLoading(false);}
    }).catch(cause=>{
      if(active){
        setDraftListError(cause instanceof ApiError?cause.message:"Rascunhos indisponíveis.");
        setDraftLoading(false);
      }
    });
    return ()=>{active=false;};
  },[tenantId]);

  const resumeDraft=(draft:CampaignDraft)=>{
    setSelectedDraft(draft);setGoal(draft.goal);
    setTicket((draft.ticket_cents/100).toFixed(2).replace(".",","));
    setBudget((draft.budget_cents/100).toFixed(2).replace(".",","));
    setCashback((draft.cashback_rate_bps/100).toString().replace(".",","));
    setOrders(String(draft.projected_paid_orders));
    setStep(2);setResult(null);setError("");setSaveError("");
    setSaveNotice("Rascunho recuperado. Revise os valores e visualize a prévia.");
  };

  const startNew=()=>{
    setSelectedDraft(null);setGoal("second_purchase");setTicket("");setBudget("");
    setCashback("2");setOrders("");setStep(1);setResult(null);
    setError("");setSaveError("");setSaveNotice("");
  };

  const saveDraft=async ()=>{
    if(!result||!canSave||saving)return;
    const input:CampaignDraftInput={
      title:selectedDraft?.title||chosen.label+" · "+new Date().toLocaleDateString("pt-BR"),
      goal, cashback_rate_bps:result.rate,
      ticket_cents:result.ticket, projected_paid_orders:result.orders,
      budget_cents:result.budget
    };
    setSaving(true);setSaveError("");setSaveNotice("");
    try{
      const saved=selectedDraft
        ?await merchantApi.updateCampaignDraft(tenantId,selectedDraft.id,selectedDraft.version,input)
        :await merchantApi.createCampaignDraft(tenantId,input);
      setSelectedDraft(saved);
      setDrafts(old=>[saved,...old.filter(entry=>entry.id!==saved.id)]
        .sort((a,b)=>b.updated_at.localeCompare(a.updated_at)));
      setSaveNotice("Rascunho salvo com segurança. Nenhum benefício foi ativado.");
    }catch(cause){
      setSaveError(cause instanceof ApiError?cause.message:"Não foi possível salvar o rascunho.");
    }finally{setSaving(false);}
  };
  const chosen=useMemo(()=>goals.find(g=>g.id===goal)!,[goal]);

  const next=(event:FormEvent)=>{
    event.preventDefault();
    setError("");
    try{setResult(parsePreview(ticket,orders,cashback,budget));setStep(3);}
    catch(e){setError(e instanceof Error?e.message:"Confira os dados informados.");}
  };

  return <div className="xp-campaign">
    <section className="xp-hero">
      <div>
        <span className="xp-eyebrow"><Sparkles size={16}/> CAMPANHAS DE FIDELIZAÇÃO</span>
        <h2>Qual resultado você<br/><em>quer para sua loja?</em></h2>
        <p>Escolha um objetivo. O Fideliza ajuda você a planejar o benefício sem começar por planilhas de margem.</p>
        <span className="xp-hero-note"><LockKeyhole size={15}/> Planejamento somente. Nenhuma campanha será publicada ou enviada.</span>
      </div>
      <div className="xp-hero-graphic" aria-hidden="true"><Gift size={64} strokeWidth={1.3}/></div>
    </section>

    <section className="xp-drafts-section" aria-label="Campanhas salvas como rascunho">
      {draftLoading && <p role="status" className="xp-draft-helper">Carregando seus rascunhos…</p>}
      {!draftLoading && draftListError && <p role="alert" className="xp-draft-error">
        Não foi possível carregar rascunhos: {draftListError}
      </p>}
      {!draftLoading && drafts.length>0 && <>
        <div className="xp-draft-heading">
          <div><span className="portal-eyebrow">CONTINUE DE ONDE PAROU</span>
            <h3>Rascunhos salvos</h3><p>Somente planejamento. Nenhuma campanha está ativa.</p></div>
          <button type="button" onClick={startNew} className="xp-draft-new">Novo planejamento</button>
        </div>
        <div className="xp-drafts-list">
          {drafts.slice(0,4).map(draft=><button
            type="button" className={"xp-draft-card"+(selectedDraft?.id===draft.id?" is-selected":"")}
            key={draft.id} onClick={()=>resumeDraft(draft)}>
            <strong>{draft.title}</strong>
            <span>{brl(draft.budget_cents)} de orçamento ·
              {(draft.cashback_rate_bps/100).toLocaleString("pt-BR")}% de cashback</span>
            <small>{new Date(draft.updated_at).toLocaleDateString("pt-BR")} · Retomar</small>
          </button>)}
        </div>
      </>}
    </section>

    <div className="xp-wizard-steps" aria-label="Etapas da criação">
      {[["1","Objetivo"],["2","Benefício"],["3","Prévia"]].map(([number,label],index)=>
        <div key={number} className={"xp-wizard-step"+(step===index+1?" is-active":"")+(step>index+1?" is-complete":"")}>
          <span>{step>index+1?<BadgeCheck size={17}/>:number}</span><strong>{label}</strong>
        </div>)}
    </div>

    <section className="xp-panel xp-wizard-panel">
      {step===1 && <>
        <div className="xp-section-heading"><span className="portal-eyebrow">ETAPA 1 DE 3</span>
          <h2>Escolha o seu objetivo</h2><p>Depois, calculamos o impacto potencial do benefício escolhido.</p></div>
        <div className="xp-goal-grid">
          {goals.map(item=>{const Icon=item.icon;return <button key={item.id} type="button"
            className={"xp-goal-card"+(goal===item.id?" selected":"")} aria-pressed={goal===item.id}
            onClick={()=>setGoal(item.id)}>
            <span className="xp-goal-icon"><Icon size={23}/></span>
            <strong>{item.title}</strong><small>{item.description}</small>
            <span className="xp-goal-check">{goal===item.id?<BadgeCheck size={18}/>:<span/>}</span>
          </button>})}
        </div>
        <div className="xp-wizard-actions"><button type="button" className="portal-primary"
          onClick={()=>setStep(2)}>Continuar <ArrowRight size={18}/></button></div>
      </>}
      {step===2 && <>
        <div className="xp-section-heading"><span className="portal-eyebrow">ETAPA 2 DE 3</span>
          <h2>Defina o limite do benefício</h2>
          <p>Não é preciso preencher custos de cada SKU para fazer uma prévia de orçamento.</p></div>
        <div className="xp-selection-summary"><Target size={17}/> Objetivo escolhido: <strong>{chosen.label}</strong>
          <button type="button" onClick={()=>{setStep(1);setError("");}}>Alterar</button></div>
        <form onSubmit={next}>
          <div className="xp-form-grid">
            <label><span>Cashback proposto (%)</span><small>Percentual ilustrativo para a próxima compra.</small>
              <select value={cashback} onChange={e=>{setCashback(e.target.value);setResult(null);}}>
                <option value="1">1%</option><option value="2">2%</option>
                <option value="3">3%</option><option value="5">5%</option>
                {!["1","2","3","5"].includes(cashback) &&
                  <option value={cashback}>{cashback}% (rascunho)</option>}
              </select></label>
            <label><span>Orçamento mensal (R$)</span><small>Quanto você poderia reservar para benefícios.</small>
              <input inputMode="decimal" value={budget} placeholder="Ex.: 300,00" aria-label="Orçamento mensal"
                onChange={e=>{setBudget(e.target.value);setResult(null);}}/></label>
            <label><span>Ticket médio estimado (R$)</span><small>Previsão manual; ainda não usamos pedidos reais.</small>
              <input inputMode="decimal" value={ticket} placeholder="Ex.: 120,00" aria-label="Ticket médio estimado"
                onChange={e=>{setTicket(e.target.value);setResult(null);}}/></label>
            <label><span>Pedidos pagos estimados</span><small>Hipótese de volume mensal, não previsão da IA.</small>
              <input inputMode="numeric" value={orders} placeholder="Ex.: 100" aria-label="Pedidos pagos estimados"
                onChange={e=>{setOrders(e.target.value);setResult(null);}}/></label>
          </div>
          <div className="xp-budget-hint"><ShieldCheck size={19}/>
            <p>Estes valores servem para dimensionar um orçamento hipotético. A análise de margem e custos reais ainda será necessária para ativar cashback.</p></div>
          {error && <div className="xp-error" role="alert">{error}</div>}
          <div className="xp-wizard-actions">
            <button className="xp-link-btn" type="button" onClick={()=>setStep(1)}><ChevronLeft size={17}/> Voltar</button>
            <button className="portal-primary" type="submit">Visualizar prévia <ArrowRight size={18}/></button>
          </div>
        </form>
      </>}
      {step===3 && result && <>
        <div className="xp-section-heading"><span className="portal-eyebrow">ETAPA 3 DE 3</span>
          <h2>Sua campanha, antes de começar</h2>
          <p>Estimativa de crédito potencial com base nas hipóteses que você informou.</p></div>
        <div className={"xp-verdict "+(result.exceed?"warning":"neutral")}>
          {result.exceed?<AlertTriangle size={22}/>:<ShieldCheck size={22}/>}
          <div><strong>{result.exceed?"O valor projetado ultrapassa o orçamento":"O cenário cabe no orçamento informado"}</strong>
            <p>{result.exceed
              ?"Reduza a taxa, o volume estimado ou ajuste o orçamento. Não indica risco de margem verificado."
              :"Apenas o teto de crédito foi comparado. Custos de mercadoria, frete, taxas e impostos ainda não foram validados."}</p></div></div>
        <div className="xp-preview-grid">
          <div><span><CircleDollarSign size={16}/> Benefício estimado por compra</span><strong>{brl(result.creditPerOrder)}</strong><small>Base: ticket médio digitado</small></div>
          <div><span><Gift size={16}/> Créditos potenciais no mês</span><strong>{brl(result.totalExposure)}</strong><small>{result.orders.toLocaleString("pt-BR")} pedidos hipotéticos</small></div>
          <div><span><ShieldCheck size={16}/> Orçamento informado</span><strong>{brl(result.budget)}</strong><small>Não é saldo disponível real</small></div>
        </div>
        <RewardPreview creditCents={result.creditPerOrder} goal={chosen.label}/>
        {selectedDraft && selectedDraft.goal===goal &&
          selectedDraft.ticket_cents===result.ticket &&
          selectedDraft.cashback_rate_bps===result.rate &&
          selectedDraft.budget_cents===result.budget &&
          selectedDraft.projected_paid_orders===result.orders &&
          <BenefitScenario tenantId={tenantId} draft={selectedDraft}
            orderAmountCents={result.ticket}/> }
        <div className="xp-budget-hint"><AlertTriangle size={19}/>
          <p><b>Ativação indisponível:</b> o motor apenas simula regras. Ainda faltam conciliação financeira, orçamento verificado e concessão controlada, estornos e resgate. Esta prévia não garante rentabilidade.</p></div>
        <div className="xp-draft-save-zone">
          <div><strong>{selectedDraft?"Atualizar rascunho":"Guardar esta campanha para depois"}</strong>
            <p>O planejamento ficará na sua loja, sem publicar promoções ou enviar mensagens.</p></div>
          <button className="portal-primary" type="button" disabled={!canSave||saving}
            onClick={()=>void saveDraft()}><Save size={17}/>
            {saving?"Salvando…":selectedDraft?"Atualizar rascunho":"Salvar rascunho"}
          </button>
        </div>
        {!canSave && <p className="xp-draft-helper">Apenas proprietário ou administrador pode salvar.</p>}
        {saveNotice && <p className="xp-draft-success" role="status">{saveNotice}</p>}
        {saveError && <p className="xp-draft-error" role="alert">{saveError}</p>}
        <div className="xp-wizard-actions">
          <button className="xp-link-btn" type="button" onClick={()=>{setStep(2);setError("");}}><ChevronLeft size={17}/> Ajustar valores</button>
          <button className="xp-link-btn" type="button" onClick={()=>setShowAdvanced(true)}>
            Revisar custos avançados <Calculator size={17}/></button>
          {selectedDraft && <button className="xp-link-btn" type="button" onClick={startNew}>
            <RefreshCw size={17}/> Novo planejamento</button>}
        </div>
      </>}
    </section>

    <section className="xp-panel xp-advanced-section">
      <div><span className="portal-eyebrow">PARA QUEM PRECISA DE MAIS CONTROLE</span>
        <h2>Análise financeira avançada</h2>
        <p>Custos por pedido, taxas, margem mínima e cenários completos. Não são obrigatórios para explorar ideias.</p></div>
      <button type="button" className="xp-link-btn" aria-expanded={showAdvanced} onClick={()=>setShowAdvanced(v=>!v)}>
        {showAdvanced?"Ocultar análise":"Abrir análise avançada"} <ChevronDown size={17}/></button>
    </section>
    {showAdvanced && <CampaignPlanner tenantId={tenantId}/>}
  </div>;
}
