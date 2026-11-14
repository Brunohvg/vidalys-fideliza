import {useEffect,useState,type FormEvent} from "react";
import {
  ArrowRight,CheckCircle2,Clock3,Gift,HeartHandshake,
  LockKeyhole,Save,ShieldCheck,UsersRound,Pencil,Trash2,X,
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
  const [editingId,setEditingId]=useState<string|null>(null);
  const [deleteConfirmId,setDeleteConfirmId]=useState<string|null>(null);
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
  const reset=()=>{
    setEditingId(null);setDeleteConfirmId(null);
    setGoal("second_purchase");setBonus("20");
    setLimit("50");setStep(1);
  };
  const edit=(draft:PointCampaignDraft)=>{
    setDeleteConfirmId(null);setEditingId(draft.id);setGoal(draft.goal);
    setBonus(String(draft.bonus_points));setLimit(String(draft.max_customers));
    setError("");setMessage("");setStep(1);
    window.scrollTo({top:0,behavior:"smooth"});
  };
  const remove=async(draft:PointCampaignDraft)=>{
    if(!canSave||busy||deleteConfirmId!==draft.id)return;
    setBusy(true);setError("");setMessage("");
    try{
      await merchantApi.deletePointCampaignDraft(tenantId,draft.id);
      setDrafts(v=>v.filter(x=>x.id!==draft.id));
      setDeleteConfirmId(null);
      if(editingId===draft.id)reset();
      setMessage("Campanha excluída. Nenhum ponto ou mensagem foi enviado.");
    }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível excluir o rascunho.");}
    finally{setBusy(false)}
  };
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
      const payload={goal,bonus_points:Number(bonus),max_customers:Number(limit)};
      const result=editingId
        ?await merchantApi.updatePointCampaignDraft(tenantId,editingId,payload)
        :await merchantApi.savePointCampaignDraft(tenantId,payload);
      setDrafts(v=>editingId?v.map(x=>x.id===editingId?result.campaign:x):[result.campaign,...v]);
      setMessage("Rascunho salvo. Nenhuma mensagem foi enviada e nenhum ponto foi concedido.");
      reset();
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
    {editingId&&<div className="vf-benefit-success" role="status">Editando campanha salva <button type="button" className="vf-benefit-advanced" onClick={reset} disabled={busy}><X size={15}/> Cancelar edição</button></div>}
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
            {busy?"Guardando…":editingId?"Salvar alterações":"Guardar rascunho"}</button>}
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
          {canSave&&<div className="vf-draft-actions">
            <button type="button" onClick={()=>edit(item)} disabled={busy}><Pencil size={16}/> Editar</button>
            {deleteConfirmId!==item.id&&<button type="button"
              onClick={()=>{setDeleteConfirmId(item.id);setError("");setMessage("");}}
              disabled={busy}><Trash2 size={16}/> Excluir</button>}
            <span className="vf-campaign-locked" title="A publicação exige carteira e regras de pontos verificadas"><LockKeyhole size={15}/> Publicação ainda não disponível</span>
          </div>}
          {canSave&&deleteConfirmId===item.id&&<div className="vf-draft-confirm"
            role="group" aria-label="Confirmação de exclusão">
            <p>Excluir este rascunho? Esta ação não pode ser desfeita.
              Nenhum cliente ou ponto será afetado.</p>
            <div className="vf-draft-confirm-actions">
              <button type="button" disabled={busy}
                onClick={()=>setDeleteConfirmId(null)}>Cancelar exclusão</button>
              <button type="button" className="danger" disabled={busy}
                onClick={()=>void remove(item)}><Trash2 size={16}/>
                {busy?"Excluindo…":"Confirmar exclusão"}</button>
            </div>
          </div>}
        </article>)}</div>}
    </section>
    <p className="vf-campaign-bottom-note">
      <CheckCircle2 size={17}/> Campanhas por e-mail, WhatsApp e recuperação de carrinhos
      serão ativadas somente após os pontos e o resgate funcionarem com segurança.
    </p>
  </div>;
}
