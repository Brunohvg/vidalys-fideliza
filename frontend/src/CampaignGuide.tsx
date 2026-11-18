import {useEffect,useState} from "react";
import {Check,Gift,HeartHandshake,Pencil,Plus,RotateCcw,Star,Trash2,X} from "lucide-react";
import {ApiError,merchantApi,type PointCampaignDraft,type PointCampaignDraftInput,type Store} from "./api";
import "./vf-ui.css";
import "./campaign-points.css";

/* Campanhas — réplica do protótipo aprovado "Dê um motivo para voltar":
   botão "Nova campanha" abre o assistente de 3 passos (objetivo, bônus, revisão)
   e a lista mostra cada campanha com o teto de pontos. Nesta etapa a campanha
   fica salva como rascunho: não envia mensagem nem concede pontos. */
type Goal=PointCampaignDraftInput["goal"];
const GOALS:{id:Goal;name:string;hint:string;Icon:typeof Gift}[]=[
 {id:"second_purchase",name:"Segunda compra",hint:"Quem comprou uma vez volta mais rápido",Icon:Gift},
 {id:"reactivation",name:"Trazer de volta",hint:"Clientes que sumiram há um tempo",Icon:RotateCcw},
 {id:"recurrence",name:"Clientes fiéis",hint:"Reconhecer quem compra sempre",Icon:HeartHandshake},
];
const BONUS=[20,50,100,200];
const PEOPLE=[20,50,100,500];
const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const TONE=["tone-purple","tone-gold","tone-green"];

export default function CampaignGuide({tenantId,role}:{tenantId:string;role:Store["role"]}){
 const canSave=role==="owner"||role==="admin";
 const [open,setOpen]=useState(false);
 const [step,setStep]=useState<1|2|3>(1);
 const [goal,setGoal]=useState<Goal>("second_purchase");
 const [bonus,setBonus]=useState(50);
 const [limit,setLimit]=useState(50);
 const [editingId,setEditingId]=useState<string|null>(null);
 const [confirmDelete,setConfirmDelete]=useState<string|null>(null);
 const [drafts,setDrafts]=useState<PointCampaignDraft[]>([]);
 const [loading,setLoading]=useState(true);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [message,setMessage]=useState("");

 useEffect(()=>{
  let active=true;setLoading(true);
  merchantApi.listPointCampaignDrafts(tenantId).then(r=>{if(active)setDrafts(r.items);})
   .catch(e=>{if(active)setError(e instanceof ApiError?e.message:"Não foi possível consultar as campanhas.");})
   .finally(()=>{if(active)setLoading(false);});
  return()=>{active=false};
 },[tenantId]);

 const cap=bonus*limit;
 const valid=Number.isInteger(bonus)&&bonus>=1&&bonus<=100000&&Number.isInteger(limit)&&limit>=1&&limit<=50000&&cap<=100_000_000;
 const goalInfo=GOALS.find(g=>g.id===goal)!;
 const start=()=>{setOpen(true);setStep(1);setEditingId(null);setGoal("second_purchase");setBonus(50);setLimit(50);setError("");setMessage("");};
 const close=()=>{setOpen(false);setEditingId(null);setStep(1);};
 const edit=(d:PointCampaignDraft)=>{setOpen(true);setStep(1);setEditingId(d.id);setGoal(d.goal);setBonus(d.bonus_points);setLimit(d.max_customers);
  setError("");setMessage("");window.scrollTo({top:0,behavior:"smooth"});};
 const next=()=>{
  if(step===1){setStep(2);return;}
  if(step===2){if(!valid){setError("Confira os pontos extras e o número de pessoas.");return;}setError("");setStep(3);return;}
  void save();
 };
 const save=async()=>{
  if(!canSave||busy||!valid)return;
  setBusy(true);setError("");setMessage("");
  try{
   const payload={goal,bonus_points:bonus,max_customers:limit};
   const r=editingId?await merchantApi.updatePointCampaignDraft(tenantId,editingId,payload):await merchantApi.savePointCampaignDraft(tenantId,payload);
   setDrafts(v=>editingId?v.map(x=>x.id===editingId?r.campaign:x):[r.campaign,...v]);
   setMessage("Campanha salva como rascunho. Nenhuma mensagem foi enviada e nenhum ponto foi concedido.");close();
  }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível salvar a campanha.");}
  finally{setBusy(false);}
 };
 const remove=async(d:PointCampaignDraft)=>{
  if(!canSave||busy)return;setBusy(true);setError("");setMessage("");
  try{await merchantApi.deletePointCampaignDraft(tenantId,d.id);setDrafts(v=>v.filter(x=>x.id!==d.id));setConfirmDelete(null);
   if(editingId===d.id)close();setMessage("Campanha excluída. Nenhum cliente ou ponto foi afetado.");}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível excluir.");}
  finally{setBusy(false);}
 };
 const numberPick=(values:number[],current:number,set:(n:number)=>void,label:string,unit:string)=><div className="vf-pills" role="group" aria-label={label}>
  {values.map(v=><button key={v} type="button" className={"vf-pill"+(current===v?" is-on":"")} aria-pressed={current===v} onClick={()=>set(v)}>{v.toLocaleString("pt-BR")} {unit}</button>)}
  <label className="vf-camp-custom"><span className="vf-sr">{label}: outro valor</span>
   <input type="number" inputMode="numeric" aria-label={label} min={1} value={current} onChange={e=>set(Math.floor(Number(e.target.value)||0))}/></label>
 </div>;

 return <section className="vf-screen vf-campaign-new" aria-labelledby="vf-camp-title">
  <div className="vf-head">
   <div><span className="vf-eyebrow">Campanhas</span><h1 id="vf-camp-title" className="vf-h1">Dê um motivo para voltar</h1>
    <span className="vf-lead">Pontos extras por tempo limitado, com teto de custo definido antes de começar.</span></div>
   {canSave&&!open&&<button type="button" className="vf-btn is-primary" onClick={start}><Plus size={18}/> Nova campanha</button>}
  </div>
  {error&&<div className="vf-toast is-error" role="alert"><X size={18}/>{error}</div>}
  {message&&<div className="vf-toast" role="status"><Check size={18}/>{message}</div>}

  {open&&<section className="vf-card is-focus vf-camp-wizard" aria-labelledby="vf-camp-new">
   <div className="vf-card-head"><h2 id="vf-camp-new" className="vf-h2">{editingId?"Editar campanha":"Nova campanha"}</h2>
    <span className="vf-chip is-soft">Passo {step} de 3</span></div>
   <div className="vf-bar" aria-hidden="true"><span style={{width:(step/3*100)+"%"}}/></div>
   {step===1&&<div className="vf-camp-step"><h3 className="vf-h3">Qual é o objetivo?</h3>
    <div className="vf-grid3">{GOALS.map(g=><button key={g.id} type="button" className={"vf-pill is-tall"+(goal===g.id?" is-on":"")} aria-pressed={goal===g.id}
     onClick={()=>setGoal(g.id)}><span>{g.name}</span><small>{g.hint}</small></button>)}</div></div>}
   {step===2&&<div className="vf-camp-step">
    <h3 className="vf-h3">Quanto de bônus?</h3>
    {numberPick(BONUS,bonus,setBonus,"Pontos extras por pessoa","pontos")}
    <h3 className="vf-h3">Para quantas pessoas, no máximo?</h3>
    {numberPick(PEOPLE,limit,setLimit,"Número máximo de pessoas","pessoas")}
    <span className="vf-muted vf-small">Teto de custo: a campanha para sozinha ao atingir {valid?cap.toLocaleString("pt-BR"):"—"} pontos extras
     {valid?` (até ${money(cap)} com o ponto a R$ 0,01)`:""}.</span>
   </div>}
   {step===3&&<div className="vf-camp-review">
    <h3 className="vf-h3">Revise antes de salvar</h3>
    <span>{goalInfo.name}: {bonus.toLocaleString("pt-BR")} pontos extras por cliente, para até {limit.toLocaleString("pt-BR")} pessoas.
     Teto de {cap.toLocaleString("pt-BR")} pontos ({money(cap)}).</span>
    <span className="vf-muted vf-small">Fica salva como rascunho. Envio de mensagens e crédito de pontos ligam quando os pontos forem liberados para a loja.</span>
   </div>}
   <div className="vf-camp-actions">
    <button type="button" className="vf-btn" onClick={()=>step===1?close():setStep(s=>(s-1) as 1|2|3)}>{step===1?"Cancelar":"Voltar"}</button>
    <button type="button" className="vf-btn is-primary" disabled={busy||(step===3&&!canSave)} onClick={next}>
     {step===3?(busy?"Salvando…":editingId?"Salvar alterações":"Salvar campanha"):"Próximo"}</button>
   </div>
  </section>}

  {loading?<p className="vf-muted" role="status">Carregando campanhas…</p>
   :drafts.length===0?<div className="vf-card"><div className="vf-empty"><strong className="vf-h3">Nenhuma campanha ainda</strong>
     <p>Comece pela segunda compra: é onde o clube mais ajuda a loja.</p></div></div>
   :<><h2 className="vf-h2">Suas campanhas</h2><div className="vf-grid2">{drafts.map((d,i)=>{const g=GOALS.find(x=>x.id===d.goal);return <article key={d.id} className="vf-card is-lift vf-camp-card">
     <div className="vf-camp-card-head"><span className={"vf-ico "+TONE[i%3]} aria-hidden="true"><Star size={20}/></span>
      <div className="vf-row-main"><strong>{g?.name??"Campanha de pontos"}</strong><span>{d.bonus_points.toLocaleString("pt-BR")} pontos extras · até {d.max_customers.toLocaleString("pt-BR")} clientes</span></div>
      <span className="vf-chip is-soft">Rascunho</span></div>
     <div className="vf-camp-cap"><div className="vf-camp-cap-label"><span className="vf-muted">Custo usado do teto</span><strong>0 de {d.maximum_bonus_points.toLocaleString("pt-BR")} pts</strong></div>
      <div className="vf-bar" aria-hidden="true"><span style={{width:"0%"}}/></div></div>
     {canSave&&(confirmDelete===d.id?<div className="vf-camp-confirm" role="group" aria-label="Confirmação de exclusão"><span className="vf-small">Excluir esta campanha?</span>
       <button type="button" className="vf-btn is-small" onClick={()=>setConfirmDelete(null)}>Cancelar exclusão</button>
       <button type="button" className="vf-btn is-small is-danger" disabled={busy} onClick={()=>void remove(d)}>Confirmar exclusão</button></div>
      :<div className="vf-pills"><button type="button" className="vf-btn is-small" onClick={()=>edit(d)}><Pencil size={15}/> Editar</button>
       <button type="button" className="vf-btn is-small" onClick={()=>setConfirmDelete(d.id)}><Trash2 size={15}/> Excluir</button></div>)}
    </article>;})}</div></>}
 </section>;
}
