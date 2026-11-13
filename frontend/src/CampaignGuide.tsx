import {useEffect,useState,type FormEvent} from "react";
import {
  ArrowRight,CheckCircle2,Clock3,Gift,HeartHandshake,
  LockKeyhole,Save,ShieldCheck,UsersRound,
} from "lucide-react";
import {
  ApiError,merchantApi,type PointCampaignDraft,type PointCampaignDraftInput,
  type Store,
} from "./api";
import "./benefit-studio.css";
import "./campaign-points.css";

const goals=[
  {id:"second_purchase",name:"Incentivar a segunda compra",
   description:"Dar um motivo para o cliente voltar depois da primeira compra.",
   icon:Gift},
  {id:"reactivation",name:"Reativar clientes",
   description:"Planejar pontos extras para quem não compra há algum tempo.",
   icon:UsersRound},
  {id:"recurrence",name:"Aumentar recorrência",
   description:"Reconhecer quem compra com frequência.",
   icon:HeartHandshake},
] as const;
type Goal=PointCampaignDraftInput["goal"];

export default function CampaignGuide({tenantId,role}:{
  tenantId:string;role:Store["role"];
}){
  const [goal,setGoal]=useState<Goal>("second_purchase");
  const [bonus,setBonus]=useState("20");
  const [limit,setLimit]=useState("50");
  const [step,setStep]=useState<1|2|3>(1);
  const [drafts,setDrafts]=useState<PointCampaignDraft[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const canSave=role==="owner"||role==="admin";
  useEffect(()=>{
    let active=true;
    setLoading(true);
    merchantApi.listPointCampaignDrafts(tenantId).then(response=>{
      if(active)setDrafts(response.items);
    }).catch(e=>{
      if(active)setError(e instanceof ApiError?e.message:"Não foi possível consultar o planejamento.");
    }).finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  },[tenantId]);
  const plannedPoints=Number(bonus)*Number(limit);
  const valid=Number.isSafeInteger(plannedPoints)
    &&Number.isInteger(Number(bonus))&&Number.isInteger(Number(limit))
    &&Number(bonus)>=1&&Number(bonus)<=100000
    &&Number(limit)>=1&&Number(limit)<=50000
    &&plannedPoints<=100000000;
  const selected=goals.find(item=>item.id===goal)!;
  const next=(e:FormEvent)=>{
    e.preventDefault();setMessage("");
    if(!valid){setError("Confira os pontos extras e o número máximo de participantes.");return}
    setError("");setStep(3);
  };
  const save=async()=>{
    if(!canSave||busy||!valid)return;
    setBusy(true);setError("");setMessage("");
    try{
      const result=await merchantApi.savePointCampaignDraft(tenantId,{
        goal,bonus_points:Number(bonus),max_customers:Number(limit),
      });
      setDrafts(v=>[result.campaign,...v]);
      setMessage("Campanha guardada como rascunho. Nenhuma mensagem foi enviada e nenhum ponto foi concedido.");
      setStep(1);
    }catch(e){setError(e instanceof ApiError?e.message:"Falha ao guardar rascunho.")}
    finally{setBusy(false)}
  };
  return <div className="vf-campaign-new">
    <header className="vf-campaign-hero">
      <span className="portal-eyebrow">AÇÕES DE RECOMPRA</span>
      <h2>Dê um motivo para o cliente voltar.</h2>
      <p>Planeje uma campanha de pontos sem configurar cálculos financeiros complexos.
        Por enquanto, nenhuma ação é publicada.</p>
      <span className="vf-benefit-state"><LockKeyhole size={14}/> Somente planejamento</span>
    </header>
    {error&&<p role="alert" className="vf-benefit-error">{error}</p>}
    {message&&<p role="status" className="vf-benefit-success">{message}</p>}
    <nav className="vf-campaign-steps" aria-label="Etapas do planejamento">
      <span className={step===1?"current":""}>1 · Objetivo</span>
      <span className={step===2?"current":""}>2 · Benefício</span>
      <span className={step===3?"current":""}>3 · Revisão</span>
    </nav>
    <section className="vf-benefit-panel">
      {step===1&&<>
        <h3>O que você quer incentivar?</h3>
        <div className="vf-campaign-goals">
          {goals.map(item=>{const Icon=item.icon;return <button
            type="button" key={item.id} aria-pressed={goal===item.id}
            className={goal===item.id?"selected":""} onClick={()=>setGoal(item.id)}>
            <Icon size={21}/><strong>{item.name}</strong><small>{item.description}</small>
          </button>})}
        </div>
        <div className="vf-campaign-actions">
          <button type="button" onClick={()=>setStep(2)}>Continuar <ArrowRight size={17}/></button>
        </div>
      </>}
      {step===2&&<>
        <h3>Qual benefício você gostaria de oferecer?</h3>
        <p>Primeiro vamos trabalhar com pontos extras. O sistema utilizará a mesma
          carteira e as regras do clube quando o motor for ativado.</p>
        <form className="vf-benefit-form" onSubmit={next}>
          <label>Pontos extras por pessoa
            <input aria-label="Pontos extras por pessoa" type="number"
              min={1} max={100000} value={bonus} onChange={e=>setBonus(e.target.value)}/>
          </label>
          <label>Número máximo de pessoas
            <input aria-label="Número máximo de pessoas" type="number"
              min={1} max={50000} value={limit} onChange={e=>setLimit(e.target.value)}/>
          </label>
          <div className="vf-benefit-summary"><ShieldCheck size={19}/>
            <span>Você está planejando distribuir no máximo
              <strong> {valid?plannedPoints.toLocaleString("pt-BR"):"—"} pontos</strong>.
              Isso não é um valor em reais nem uma estimativa de lucro.</span>
          </div>
          <div className="vf-campaign-actions">
            <button type="button" className="secondary" onClick={()=>setStep(1)}>Voltar</button>
            <button type="submit">Revisar campanha <ArrowRight size={17}/></button>
          </div>
        </form>
      </>}
      {step===3&&<>
        <h3>Sua campanha, antes de publicar</h3>
        <div className="vf-campaign-recap">
          <div><span>Objetivo</span><strong>{selected.name}</strong></div>
          <div><span>Benefício sugerido</span><strong>{Number(bonus)} pontos extras</strong></div>
          <div><span>Limite</span><strong>{Number(limit)} pessoas</strong></div>
          <div><span>Exposição máxima</span><strong>{plannedPoints.toLocaleString("pt-BR")} pontos</strong></div>
        </div>
        <p className="vf-campaign-warning"><ShieldCheck size={17}/>
          Esses pontos não equivalem automaticamente a dinheiro.
          O custo real dependerá das recompensas, da taxa de resgate e das margens.
          A campanha não envia e-mail, WhatsApp nem crédito nesta etapa.</p>
        <div className="vf-campaign-actions">
          <button type="button" className="secondary" onClick={()=>setStep(2)}>Ajustar</button>
          {canSave&&<button type="button" disabled={busy}
            onClick={()=>void save()}><Save size={17}/>
            {busy?"Guardando…":"Guardar rascunho"}</button>}
        </div>
      </>}
    </section>
    <section className="vf-benefit-panel">
      <h3>Rascunhos salvos</h3>
      {loading?<p role="status">Carregando…</p>:
        drafts.length===0?<p>Nenhuma campanha salva. Comece pelo objetivo acima.</p>:
        <div className="vf-benefit-grid">{drafts.map(item=><article
          key={item.id} className="vf-benefit-card">
          <span><Clock3 size={15}/> Não publicada</span>
          <h4>{goals.find(v=>v.id===item.goal)?.name||"Campanha de pontos"}</h4>
          <strong>{item.bonus_points.toLocaleString("pt-BR")} pontos extras</strong>
          <p>Até {item.max_customers.toLocaleString("pt-BR")} clientes</p>
          <small>Nenhum cliente foi contatado ou pontuado.</small>
        </article>)}</div>}
    </section>
    <p className="vf-campaign-bottom-note">
      <CheckCircle2 size={17}/> Campanhas por e-mail, WhatsApp e recuperação de carrinhos
      serão ativadas somente após os pontos e o resgate funcionarem com segurança.
    </p>
  </div>;
}
