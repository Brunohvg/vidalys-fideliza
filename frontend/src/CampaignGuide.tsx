import {useEffect,useMemo,useRef,useState} from "react";
import {CalendarDays,Cake,Check,Gift,Pencil,Plus,Repeat2,RotateCcw,Sparkles,Target,Trash2,Users,X,Zap} from "lucide-react";
import {ApiError,merchantApi,type CampaignAudience,type CampaignGoal,type PointCampaignDraft,type PointCampaignDraftInput,type Store} from "./api";
import "./vf-ui.css";
import "./campaign-points.css";

/* Campanhas inteligentes. O lojista escolhe um modelo, o sistema conta quem
   se encaixa com as vendas reais, mostra o custo máximo, separa um grupo de
   comparação e mostra como o cliente vai ver a oferta no Meu Clube.
   Publicar só exibe a oferta: nenhum ponto é creditado e nada é enviado
   enquanto a carteira de pontos estiver travada. */

type Template={id:CampaignGoal;name:string;pitch:string;why:string;Icon:typeof Gift;tone:string;bonus:number;days:number};
const TEMPLATES:Template[]=[
 {id:"second_purchase",name:"Segunda compra",pitch:"Para quem comprou uma vez nos últimos dias",why:"A segunda compra é onde a maioria dos clientes se perde.",Icon:Gift,tone:"tone-purple",bonus:100,days:15},
 {id:"reactivation",name:"Trazer de volta",pitch:"Para quem não compra há um tempo",why:"Um prazo curto cria motivo para voltar agora.",Icon:RotateCcw,tone:"tone-rose",bonus:200,days:15},
 {id:"near_reward",name:"Quase lá",pitch:"Para quem está perto de uma troca",why:"Quem está perto de completar responde mais rápido.",Icon:Target,tone:"tone-gold",bonus:50,days:10},
 {id:"multiplier",name:"Pontos em dobro",pitch:"Para todo o clube, por poucos dias",why:"Bom para datas fracas do calendário. Sempre com teto.",Icon:Zap,tone:"tone-purple",bonus:300,days:7},
 {id:"birthday",name:"Aniversariantes",pitch:"Para quem faz aniversário no mês",why:"O cliente informa o aniversário no perfil do Meu Clube.",Icon:Cake,tone:"tone-gold",bonus:150,days:30},
 {id:"recurrence",name:"Clientes fiéis",pitch:"Para todo o clube, compra após compra",why:"Reconhece quem já volta sempre.",Icon:Repeat2,tone:"tone-green",bonus:50,days:30},
];
const BONUS=[50,100,200,500];
const PEOPLE=[50,100,500,2000];
const LENGTHS=[7,15,30];
const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const n=(v:number)=>v.toLocaleString("pt-BR");
const iso=(d:Date)=>new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,10);
const addDays=(base:string,days:number)=>{const d=new Date(base+"T12:00:00");d.setDate(d.getDate()+days);return iso(d);};
const shortDate=(value:string|null)=>value?new Date(value+"T12:00:00").toLocaleDateString("pt-BR",{day:"2-digit",month:"short"}):"—";
const template=(goal:CampaignGoal)=>TEMPLATES.find(t=>t.id===goal)??TEMPLATES[0];
const STATUS:Record<PointCampaignDraft["status"],{label:string;chip:string}>={
 draft:{label:"Rascunho",chip:"is-soft"},scheduled:{label:"Agendada",chip:"is-gold"},
 live:{label:"No Meu Clube",chip:"is-ok"},ended:{label:"Encerrada",chip:"is-soft"},
};

type Form=Required<Omit<PointCampaignDraftInput,"starts_on"|"ends_on">>&{starts_on:string;ends_on:string};
const blank=(goal:CampaignGoal="second_purchase"):Form=>{
 const t=template(goal);const today=iso(new Date());
 return {goal,bonus_points:t.bonus,max_customers:100,title:"",message:"",starts_on:today,ends_on:addDays(today,t.days),
  window_days:30,inactive_days:60,near_points:100,multiplier:2,holdout_percent:10};
};

function offerText(f:Form){
 const p=n(f.bonus_points);const when=shortDate(f.ends_on);
 const map:Record<CampaignGoal,[string,string]>={
  second_purchase:["Volte e ganhe +"+p+" pontos","Na sua próxima compra até "+when+", você ganha "+p+" pontos extras."],
  reactivation:["Sentimos sua falta: +"+p+" pontos","Compre até "+when+" e ganhe "+p+" pontos extras."],
  recurrence:["Compre de novo e ganhe +"+p+" pontos","Cada compra até "+when+" rende "+p+" pontos extras."],
  near_reward:["Você está quase lá","Compre até "+when+" e ganhe "+p+" pontos extras para completar sua troca."],
  multiplier:["Pontos em dobro","Compras até "+when+" valem "+f.multiplier+"× pontos (até "+p+" pontos extras)."],
  birthday:["Feliz aniversário! +"+p+" pontos","Presente da loja: compre até "+when+" e ganhe "+p+" pontos extras."],
 };
 const [title,message]=map[f.goal];
 return {title:f.title.trim()||title,message:f.message.trim()||message};
}

export default function CampaignGuide({tenantId,role}:{tenantId:string;role:Store["role"]}){
 const canSave=role==="owner"||role==="admin";
 const [open,setOpen]=useState(false);
 const [step,setStep]=useState<1|2|3|4>(1);
 const [form,setForm]=useState<Form>(blank());
 const [editingId,setEditingId]=useState<string|null>(null);
 const [confirmDelete,setConfirmDelete]=useState<string|null>(null);
 const [items,setItems]=useState<PointCampaignDraft[]>([]);
 const [loading,setLoading]=useState(true);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const [counts,setCounts]=useState<Partial<Record<CampaignGoal,number>>>({});
 const [audience,setAudience]=useState<CampaignAudience|null>(null);
 const [counting,setCounting]=useState(false);
 const wizardRef=useRef<HTMLElement>(null);

 useEffect(()=>{
  let active=true;setLoading(true);
  merchantApi.listPointCampaignDrafts(tenantId).then(r=>{if(active)setItems(r.items);})
   .catch(e=>{if(active)setError(e instanceof ApiError?e.message:"Não foi possível consultar as campanhas.");})
   .finally(()=>{if(active)setLoading(false);});
  return()=>{active=false};
 },[tenantId]);

 // Quantos clientes cada modelo alcança hoje (vendas reais da loja).
 useEffect(()=>{
  if(!open||step!==1)return;
  let active=true;
  Promise.all(TEMPLATES.map(t=>merchantApi.previewCampaignAudience(tenantId,{goal:t.id,bonus_points:t.bonus,max_customers:50000,holdout_percent:0})
   .then(r=>[t.id,r.audience.eligible] as const).catch(()=>[t.id,-1] as const)))
   .then(rows=>{if(active)setCounts(Object.fromEntries(rows.filter(r=>r[1]>=0)));});
  return()=>{active=false};
 },[open,step,tenantId]);

 const valid=form.bonus_points>=1&&form.bonus_points<=100000&&form.max_customers>=1&&form.max_customers<=50000
  &&form.bonus_points*form.max_customers<=100_000_000&&Boolean(form.starts_on&&form.ends_on)&&form.ends_on>=form.starts_on;
 const payload=useMemo(()=>({...form,title:form.title.trim(),message:form.message.trim()}),[form]);

 // Prévia ao vivo do público e do custo nos passos 2 a 4.
 useEffect(()=>{
  if(!open||step===1||!valid)return;
  let active=true;setCounting(true);
  const timer=window.setTimeout(()=>{
   merchantApi.previewCampaignAudience(tenantId,payload).then(r=>{if(active)setAudience(r.audience);})
    .catch(()=>{if(active)setAudience(null);}).finally(()=>{if(active)setCounting(false);});
  },350);
  return()=>{active=false;window.clearTimeout(timer);};
 },[open,step,payload,valid,tenantId]);

 const set=<K extends keyof Form>(key:K,value:Form[K])=>setForm(f=>({...f,[key]:value}));
 const start=()=>{setOpen(true);setStep(1);setEditingId(null);setForm(blank());setAudience(null);setError("");setNotice("");};
 const close=()=>{setOpen(false);setEditingId(null);setStep(1);};
 const pick=(goal:CampaignGoal)=>{setForm(f=>({...blank(goal),max_customers:f.max_customers}));setStep(2);};
 const edit=(c:PointCampaignDraft)=>{
  setOpen(true);setStep(2);setEditingId(c.id);setError("");setNotice("");
  setForm({goal:c.goal,bonus_points:c.bonus_points,max_customers:c.max_customers,title:c.title,message:c.message,
   starts_on:c.starts_on??iso(new Date()),ends_on:c.ends_on??addDays(iso(new Date()),template(c.goal).days),
   window_days:c.window_days,inactive_days:c.inactive_days,near_points:c.near_points,multiplier:c.multiplier,holdout_percent:c.holdout_percent});
  window.requestAnimationFrame(()=>wizardRef.current?.scrollIntoView({block:"start",behavior:"smooth"}));
 };
 const save=async(publish:boolean)=>{
  if(!canSave||busy||!valid)return;
  setBusy(true);setError("");setNotice("");
  try{
   let saved=(editingId?await merchantApi.updatePointCampaignDraft(tenantId,editingId,payload)
    :await merchantApi.savePointCampaignDraft(tenantId,payload)).campaign;
   if(publish&&!saved.published) saved=(await merchantApi.publishPointCampaign(tenantId,saved.id,true)).campaign;
   setItems(v=>v.some(x=>x.id===saved.id)?v.map(x=>x.id===saved.id?saved:x):[saved,...v]);
   setNotice(publish?"Campanha publicada no Meu Clube. Os clientes do público veem a oferta; os pontos extras entram quando a carteira for liberada."
    :"Campanha salva como rascunho. Nada aparece para o cliente até você publicar.");
   close();
  }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível salvar a campanha.");}
  finally{setBusy(false);}
 };
 const toggle=async(c:PointCampaignDraft)=>{
  if(!canSave||busy)return;setBusy(true);setError("");setNotice("");
  try{const r=await merchantApi.publishPointCampaign(tenantId,c.id,!c.published);
   setItems(v=>v.map(x=>x.id===c.id?r.campaign:x));
   setNotice(r.campaign.published?"Campanha publicada no Meu Clube.":"Campanha tirada do Meu Clube. Ela continua salva.");}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível alterar a campanha.");}
  finally{setBusy(false);}
 };
 const remove=async(c:PointCampaignDraft)=>{
  if(!canSave||busy)return;setBusy(true);setError("");setNotice("");
  try{await merchantApi.deletePointCampaignDraft(tenantId,c.id);setItems(v=>v.filter(x=>x.id!==c.id));setConfirmDelete(null);
   if(editingId===c.id)close();setNotice("Campanha excluída. Nenhum cliente ou ponto foi afetado.");}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível excluir.");}
  finally{setBusy(false);}
 };
 const numberPick=(values:number[],current:number,onPick:(v:number)=>void,label:string,unit:string)=><div className="vf-pills" role="group" aria-label={label}>
  {values.map(v=><button key={v} type="button" className={"vf-pill"+(current===v?" is-on":"")} aria-pressed={current===v} onClick={()=>onPick(v)}>{n(v)} {unit}</button>)}
  <label className="vf-camp-custom"><span className="vf-sr">{label}: outro valor</span>
   <input type="number" inputMode="numeric" aria-label={label} min={1} value={current} onChange={e=>onPick(Math.max(0,Math.floor(Number(e.target.value)||0)))}/></label>
 </div>;

 const t=template(form.goal);
 const preview=offerText(form);
 const days=form.starts_on&&form.ends_on?Math.round((new Date(form.ends_on).getTime()-new Date(form.starts_on).getTime())/86400000):0;
 const live=items.filter(c=>c.status==="live").length;

 return <section className="vf-screen vf-campaign-new" aria-labelledby="vf-camp-title">
  <div className="vf-head">
   <div><span className="vf-eyebrow">Campanhas</span><h1 id="vf-camp-title" className="vf-h1">Dê um motivo para voltar</h1>
    <span className="vf-lead">Ofertas de pontos com público certo, prazo e custo máximo, e uma comparação honesta do resultado.</span></div>
   {canSave&&!open&&<button type="button" className="vf-btn is-primary" onClick={start}><Plus size={18}/> Nova campanha</button>}
  </div>
  {error&&<div className="vf-toast is-error" role="alert"><X size={18}/>{error}</div>}
  {notice&&<div className="vf-toast" role="status"><Check size={18}/>{notice}</div>}

  {open&&<section ref={wizardRef} className="vf-card is-focus vf-camp-wizard" aria-labelledby="vf-camp-new">
   <div className="vf-card-head"><h2 id="vf-camp-new" className="vf-h2">{editingId?"Editar campanha":"Nova campanha"}</h2>
    <span className="vf-chip is-soft">Passo {step} de 4</span></div>
   <div className="vf-bar" aria-hidden="true"><span style={{width:(step/4*100)+"%"}}/></div>

   {step===1&&<div className="vf-camp-step"><h3 className="vf-h3">Qual é o objetivo?</h3>
    <div className="vf-camp-templates">{TEMPLATES.map(item=><button key={item.id} type="button" className={"vf-camp-template"+(form.goal===item.id?" is-on":"")}
     aria-pressed={form.goal===item.id} onClick={()=>pick(item.id)}>
     <span className={"vf-ico "+item.tone} aria-hidden="true"><item.Icon size={20}/></span>
     <strong>{item.name}</strong><span>{item.pitch}</span>
     <span className="vf-camp-count"><Users size={14} aria-hidden="true"/>{counts[item.id]===undefined?"contando…":n(counts[item.id] as number)+(counts[item.id]===1?" cliente hoje":" clientes hoje")}</span>
    </button>)}</div></div>}

   {step===2&&<div className="vf-camp-split"><div className="vf-camp-step">
    <div className="vf-camp-picked"><span className={"vf-ico "+t.tone} aria-hidden="true"><t.Icon size={20}/></span>
     <div><strong>{t.name}</strong><span className="vf-muted vf-small">{t.why}</span></div></div>
    {form.goal==="second_purchase"&&<label className="vf-field is-compact">Primeira compra nos últimos (dias)
     <input type="number" min={1} max={365} value={form.window_days} onChange={e=>set("window_days",Math.floor(Number(e.target.value)||0))}/></label>}
    {form.goal==="reactivation"&&<><h3 className="vf-h3">Sem comprar há quanto tempo?</h3>
     <div className="vf-pills" role="group" aria-label="Dias sem comprar">{[60,90,120].map(v=><button key={v} type="button" className={"vf-pill"+(form.inactive_days===v?" is-on":"")}
      aria-pressed={form.inactive_days===v} onClick={()=>set("inactive_days",v)}>{v} dias</button>)}</div></>}
    {form.goal==="near_reward"&&<label className="vf-field is-compact">Faltando até quantos pontos para a troca
     <input type="number" min={1} value={form.near_points} onChange={e=>set("near_points",Math.floor(Number(e.target.value)||0))}/></label>}
    {form.goal==="multiplier"&&<><h3 className="vf-h3">Multiplicar por</h3>
     <div className="vf-pills" role="group" aria-label="Multiplicador">{[2,3].map(v=><button key={v} type="button" className={"vf-pill"+(form.multiplier===v?" is-on":"")}
      aria-pressed={form.multiplier===v} onClick={()=>set("multiplier",v)}>{v}× pontos</button>)}</div></>}
    <h3 className="vf-h3">Quanto de bônus?</h3>
    {numberPick(BONUS,form.bonus_points,v=>set("bonus_points",v),form.goal==="multiplier"?"Pontos extras por pessoa (teto)":"Pontos extras por pessoa","pontos")}
    <h3 className="vf-h3">Para quantas pessoas, no máximo?</h3>
    {numberPick(PEOPLE,form.max_customers,v=>set("max_customers",v),"Número máximo de pessoas","pessoas")}
   </div><AudiencePanel audience={audience} counting={counting} form={form} valid={valid}/></div>}

   {step===3&&<div className="vf-camp-split"><div className="vf-camp-step">
    <h3 className="vf-h3">Quando?</h3>
    <div className="vf-pills" role="group" aria-label="Duração">{LENGTHS.map(v=><button key={v} type="button" className={"vf-pill"+(days===v?" is-on":"")}
     aria-pressed={days===v} onClick={()=>set("ends_on",addDays(form.starts_on,v))}>{v} dias</button>)}</div>
    <div className="vf-camp-dates">
     <label className="vf-field is-compact">Começa em<input type="date" value={form.starts_on} onChange={e=>set("starts_on",e.target.value)}/></label>
     <label className="vf-field is-compact">Termina em<input type="date" value={form.ends_on} min={form.starts_on} onChange={e=>set("ends_on",e.target.value)}/></label>
    </div>
    <h3 className="vf-h3">Grupo de comparação</h3>
    <div className="vf-pills" role="group" aria-label="Grupo de comparação">{[0,10,20].map(v=><button key={v} type="button" className={"vf-pill"+(form.holdout_percent===v?" is-on":"")}
     aria-pressed={form.holdout_percent===v} onClick={()=>set("holdout_percent",v)}>{v===0?"Sem comparação":v+"% de fora"}</button>)}</div>
    <span className="vf-muted vf-small">{form.holdout_percent>0?"Uma parte do público não recebe a oferta. No fim, você compara quem voltou nos dois grupos e vê o efeito real da campanha."
     :"Sem grupo de comparação não dá para saber se a campanha trouxe a venda ou se o cliente voltaria de qualquer jeito."}</span>
    <details className="vf-camp-text"><summary>Personalizar o texto para o cliente</summary>
     <label className="vf-field is-compact">Título<input maxLength={80} value={form.title} placeholder={offerText({...form,title:""}).title} onChange={e=>set("title",e.target.value)}/></label>
     <label className="vf-field is-compact">Mensagem<input maxLength={180} value={form.message} placeholder={offerText({...form,message:""}).message} onChange={e=>set("message",e.target.value)}/></label>
    </details>
   </div><OfferPreview title={preview.title} message={preview.message} goal={form.goal} ends={form.ends_on}/></div>}

   {step===4&&<div className="vf-camp-split"><div className="vf-camp-review">
    <h3 className="vf-h3">Revise antes de publicar</h3>
    <dl className="vf-camp-facts">
     <div><dt>Modelo</dt><dd>{t.name}</dd></div>
     <div><dt>Bônus</dt><dd>{form.goal==="multiplier"?form.multiplier+"× pontos, até "+n(form.bonus_points)+" extras":n(form.bonus_points)+" pontos extras"} por pessoa</dd></div>
     <div><dt>Período</dt><dd>{shortDate(form.starts_on)} a {shortDate(form.ends_on)} ({days} dias)</dd></div>
     <div><dt>Público hoje</dt><dd>{audience?n(audience.reached)+" clientes"+(audience.comparison?" + "+n(audience.comparison)+" na comparação":""):"—"}</dd></div>
     <div><dt>Custo máximo</dt><dd><strong>{audience?money(audience.max_cost_cents):"—"}</strong>{audience&&audience.reached<form.max_customers?" (até "+money(audience.max_cost_if_full_cents)+" se o público crescer)":""}</dd></div>
    </dl>
    <span className="vf-muted vf-small">Publicar mostra a oferta no Meu Clube para o público escolhido. Nenhum ponto é creditado e nada é enviado
     enquanto a carteira de pontos estiver travada: o cliente vê o aviso de que os pontos entram quando a loja ativar.</span>
   </div><OfferPreview title={preview.title} message={preview.message} goal={form.goal} ends={form.ends_on}/></div>}

   <div className="vf-camp-actions">
    <button type="button" className="vf-btn" onClick={()=>step===1||(step===2&&editingId)?close():setStep(s=>(s-1) as 1|2|3|4)}>{step===1||(step===2&&editingId)?"Cancelar":"Voltar"}</button>
    {step>1&&step<4&&<button type="button" className="vf-btn is-primary" disabled={!valid} onClick={()=>{if(!valid){setError("Confira pontos, pessoas e datas.");return;}setError("");setStep(s=>(s+1) as 1|2|3|4);}}>Próximo</button>}
    {step===4&&<>
     <button type="button" className="vf-btn" disabled={busy||!canSave} onClick={()=>void save(false)}>{busy?"Salvando…":"Salvar rascunho"}</button>
     <button type="button" className="vf-btn is-primary" disabled={busy||!canSave} onClick={()=>void save(true)}><Sparkles size={17}/> {busy?"Publicando…":"Publicar no Meu Clube"}</button>
    </>}
   </div>
  </section>}

  {loading?<p className="vf-muted" role="status">Carregando campanhas…</p>
   :items.length===0?<div className="vf-card"><div className="vf-empty"><strong className="vf-h3">Nenhuma campanha ainda</strong>
     <p>Comece pela segunda compra: é onde o clube mais ajuda a loja.</p></div></div>
   :<><div className="vf-camp-list-head"><h2 className="vf-h2">Suas campanhas</h2>{live>0&&<span className="vf-chip is-ok">{live} no Meu Clube agora</span>}</div>
    <div className="vf-grid2">{items.map(c=>{const tp=template(c.goal);const st=STATUS[c.status];
     return <article key={c.id} className="vf-card is-lift vf-camp-card">
      <div className="vf-camp-card-head"><span className={"vf-ico "+tp.tone} aria-hidden="true"><tp.Icon size={20}/></span>
       <div className="vf-row-main"><strong>{c.display_title}</strong><span>{tp.name} · {c.starts_on?shortDate(c.starts_on)+" a "+shortDate(c.ends_on):"sem período"}</span></div>
       <span className={"vf-chip "+st.chip}>{st.label}</span></div>
      <div className="vf-camp-metrics">
       <div><span>Público</span><strong>{n(c.audience.reached)}</strong></div>
       <div><span>Bônus</span><strong>{n(c.bonus_points)} pts</strong></div>
       <div><span>Custo máximo</span><strong>{money(c.audience.max_cost_cents)}</strong></div>
      </div>
      <CampaignResult c={c}/>
      {canSave&&(confirmDelete===c.id?<div className="vf-camp-confirm" role="group" aria-label="Confirmação de exclusão"><span className="vf-small">Excluir esta campanha?</span>
        <button type="button" className="vf-btn is-small" onClick={()=>setConfirmDelete(null)}>Cancelar exclusão</button>
        <button type="button" className="vf-btn is-small is-danger" disabled={busy} onClick={()=>void remove(c)}>Confirmar exclusão</button></div>
       :<div className="vf-pills">
        {c.status!=="ended"&&<button type="button" className={"vf-btn is-small"+(c.published?"":" is-primary")} disabled={busy} onClick={()=>void toggle(c)}>
         {c.published?"Tirar do Meu Clube":"Publicar"}</button>}
        <button type="button" className="vf-btn is-small" onClick={()=>edit(c)}><Pencil size={15}/> Editar</button>
        <button type="button" className="vf-btn is-small" onClick={()=>setConfirmDelete(c.id)}><Trash2 size={15}/> Excluir</button></div>)}
     </article>;})}</div></>}
 </section>;
}

function AudiencePanel({audience,counting,form,valid}:{audience:CampaignAudience|null;counting:boolean;form:Form;valid:boolean}){
 return <aside className="vf-camp-panel" aria-label="Público e custo" aria-live="polite">
  <span className="vf-eyebrow">Público e custo</span>
  {!valid?<p className="vf-muted vf-small">Escolha pontos e pessoas para calcular.</p>
  :!audience?<p className="vf-muted vf-small">{counting?"Contando clientes…":"Não foi possível contar agora."}</p>
  :<>
   <div className="vf-camp-panel-big"><strong>{n(audience.reached)}</strong><span>{audience.reached===1?"cliente recebe":"clientes recebem"}</span></div>
   <ul className="vf-camp-panel-list">
    <li><span>Se encaixam hoje</span><b>{n(audience.eligible)}</b></li>
    <li><span>Grupo de comparação</span><b>{n(audience.comparison)}</b></li>
    <li><span>Limite de pessoas</span><b>{n(form.max_customers)}</b></li>
   </ul>
   <div className="vf-camp-cost"><span>Custo máximo</span><strong>{money(audience.max_cost_cents)}</strong>
    <small>{n(form.bonus_points)} pontos × {n(audience.reached)} clientes · 1 ponto = R$ 0,01</small></div>
   {audience.eligible===0&&<p className="vf-camp-hint">Ninguém se encaixa ainda. {form.goal==="birthday"?"Os clientes informam o aniversário no perfil do Meu Clube.":form.goal==="near_reward"?"Precisa de saldo de pontos e de uma recompensa publicada.":"As vendas registradas no balcão e na Nuvemshop alimentam esta conta."}</p>}
  </>}
 </aside>;
}

function OfferPreview({title,message,goal,ends}:{title:string;message:string;goal:CampaignGoal;ends:string}){
 const Icon=template(goal).Icon;
 return <aside className="vf-camp-phone" aria-label="Como o cliente vê no Meu Clube">
  <span className="vf-eyebrow">Como o cliente vê</span>
  <div className="vf-camp-phone-screen">
   <span className="vf-camp-phone-label">Para você</span>
   <div className="vf-camp-offer">
    <span className="vf-camp-offer-ico" aria-hidden="true"><Icon size={20}/></span>
    <div><strong>{title}</strong><span>{message}</span>
     <em><CalendarDays size={13} aria-hidden="true"/> até {shortDate(ends)}</em></div>
   </div>
   <span className="vf-camp-phone-note">Os pontos entram quando a loja ativar o clube.</span>
  </div>
 </aside>;
}

function CampaignResult({c}:{c:PointCampaignDraft}){
 const r=c.result;
 if(!r) return c.published?null:<p className="vf-muted vf-small">O resultado aparece aqui depois que a campanha começar.</p>;
 const rate=(a:number,b:number)=>b?Math.round(a/b*100):null;
 const mine=rate(r.reached_returned,r.reached);const base=rate(r.comparison_returned,r.comparison);
 return <div className="vf-camp-result" aria-label="Resultado da campanha">
  <div><span>Voltaram a comprar</span><strong>{mine===null?"—":mine+"%"}</strong><small>{n(r.reached_returned)} de {n(r.reached)} que receberam</small></div>
  <div><span>Sem a oferta</span><strong>{base===null?"—":base+"%"}</strong><small>{r.comparison?n(r.comparison_returned)+" de "+n(r.comparison)+" na comparação":"sem grupo de comparação"}</small></div>
  <p className="vf-muted vf-small">{mine!==null&&base!==null&&r.reached>=30&&r.comparison>=30
   ?"Diferença de "+(mine-base)+" pontos percentuais. Comparação simples: confirme com mais tempo antes de concluir."
   :"Poucos clientes para concluir. Use como sinal, não como prova."}</p>
 </div>;
}
