import {useEffect,useMemo,useState,type FormEvent} from "react";
import {AlertTriangle,Check,Copy,ExternalLink,FlaskConical,Link2,Plus,ShoppingBag,Smartphone,Trash2,X} from "lucide-react";
import EnrollmentManagement from "./EnrollmentManagement";
import LoyaltyTrialPanel from "./LoyaltyTrialPanel";
import {ApiError,merchantApi,type DiscountRewardDraft,type PointRuleDraft,type Store} from "./api";
import {summarizeClub} from "./club-summary";
import "./vf-ui.css";
import "./program-hub.css";

/* Meu clube — réplica do protótipo aprovado "Como seu clube funciona".
   1. Como ganhar: uma decisão (quanto devolver), quando libera e validade.
   2. Como usar: faixas de troca com o preço do ponto fixo (1 ponto = R$ 0,01).
   3. Quem participa: link, página do cliente, regulamento e adesões.
   4. Testar: simulação sem publicar. Nada aqui credita pontos ou cria cupom. */
export type ProgramArea="rewards"|"earning"|"participants"|"testing";
type Tab="ganhar"|"usar"|"participar"|"testar";
const tabFor:Record<ProgramArea,Tab>={earning:"ganhar",rewards:"usar",participants:"participar",testing:"testar"};

const PCTS=[1,2,3,5];
const HOLDS:[number,string][]=[[0,"Na hora"],[7,"7 dias"],[15,"15 dias"],[30,"30 dias"]];
const VALIDITY:[number,string][]=[[180,"6 meses"],[365,"1 ano"],[730,"2 anos"]];
const DISCOUNTS=[500,1000,2000,5000];
const POINT_CENTS=1; // preço do ponto nas faixas criadas aqui
const money=(cents:number)=>(cents/100).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const moneyShort=(cents:number)=>money(cents).replace(",00","");
const pct=(value:number)=>value.toLocaleString("pt-BR",{maximumFractionDigits:2})+"%";
const period=(days:number)=>days%365===0?`${days/365} ano${days===365?"":"s"}`:days%30===0&&days>=60?`${days/30} meses`:`${days} dia${days===1?"":"s"}`;
const toCents=(raw:string)=>{const c=raw.trim().replace(/^R\$\s*/i,"");if(!/^\d{1,6}(?:[,.]\d{1,2})?$/.test(c))return null;
 const [w,d=""]=c.replace(",",".").split(".");return Number(w)*100+Number(d.padEnd(2,"0"));};

export default function ProgramHub({tenantId,role,storeSlug,tenantStatus,initialArea="earning",onViewClients}:{
 tenantId:string;role:Store["role"];storeSlug:string;tenantStatus:Store["status"];platform?:Store["platform"];
 initialArea?:ProgramArea;onViewClients:()=>void;onViewSales?:()=>void;onOpenSettings?:()=>void;
}){
 const canEdit=role==="owner"||role==="admin";
 const [tab,setTab]=useState<Tab>(tabFor[initialArea]);
 const [rule,setRule]=useState<PointRuleDraft|null>(null);
 const [rewards,setRewards]=useState<DiscountRewardDraft[]>([]);
 const [loading,setLoading]=useState(true);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [message,setMessage]=useState("");
 const [refresh,setRefresh]=useState(0);
 // regra em edição
 const [draftPct,setDraftPct]=useState<number|null>(null);
 const [hold,setHold]=useState(7);
 const [validity,setValidity]=useState(365);
 // nova faixa
 const [tierOpen,setTierOpen]=useState(false);
 const [tierDiscount,setTierDiscount]=useState("10,00");
 const [tierMin,setTierMin]=useState("");
 const [tierLimit,setTierLimit]=useState("1000");
 const [confirm,setConfirm]=useState<{id:string;kind:"publish"|"delete"}|null>(null);
 const [copied,setCopied]=useState(false);

 useEffect(()=>{
  if(!canEdit){setLoading(false);return;}
  let active=true;setLoading(true);setError("");
  Promise.all([merchantApi.getPointRuleDraft(tenantId),merchantApi.listDiscountRewardDrafts(tenantId)]).then(([r,w])=>{
   if(!active)return;
   setRule(r.rule);setRewards(w.items);
   if(r.rule){setDraftPct(r.rule.points*100/r.rule.per_cents);setHold(r.rule.hold_days);setValidity(r.rule.validity_days);}
   else{setDraftPct(2);setHold(7);setValidity(365);}
  }).catch(e=>{if(active)setError(e instanceof ApiError?e.message:"Não foi possível carregar o clube.");})
   .finally(()=>{if(active)setLoading(false);});
  return()=>{active=false};
 },[tenantId,canEdit,refresh]);

 const currentPct=rule?rule.points*100/rule.per_cents:null;
 const pctOptions=useMemo(()=>currentPct!==null&&!PCTS.includes(currentPct)?[...PCTS,currentPct].sort((a,b)=>a-b):PCTS,[currentPct]);
 const holdOptions=useMemo(()=>HOLDS.some(([d])=>d===hold)?HOLDS:[...HOLDS,[hold,`${hold} dias`] as [number,string]].sort((a,b)=>a[0]-b[0]),[hold]);
 const validityOptions=useMemo(()=>VALIDITY.some(([d])=>d===validity)?VALIDITY:[...VALIDITY,[validity,period(validity)] as [number,string]].sort((a,b)=>a[0]-b[0]),[validity]);
 const dirty=draftPct!==null&&(!rule||draftPct!==currentPct||hold!==rule.hold_days||validity!==rule.validity_days);
 const summary=summarizeClub(rule,rewards);
 const p=draftPct??0;
 const examplePoints=Math.round(p*100); // compra de R$ 100 com ponto de R$ 0,01
 const earnPoints=(pctValue:number)=>{
  // representa a porcentagem como "N pontos a cada R$ X" com inteiros
  for(const per of [100,200,500,1000]){const pts=pctValue*per/100;if(Number.isInteger(pts)&&pts>=1)return {points:pts,per_cents:per};}
  return null;
 };

 const saveRule=async()=>{
  if(!canEdit||busy||draftPct===null)return;
  const shape=earnPoints(draftPct);
  if(!shape){setError("Escolha uma porcentagem da lista.");return;}
  setBusy(true);setError("");setMessage("");
  try{
   await merchantApi.savePointRuleDraft(tenantId,{...shape,hold_days:hold,validity_days:validity});
   setMessage("Regra salva. O resumo do clube já usa os novos valores.");setRefresh(v=>v+1);
  }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível salvar a regra.");}
  finally{setBusy(false);}
 };
 const createTier=async(event:FormEvent)=>{
  event.preventDefault();if(!canEdit||busy)return;
  const discount=toCents(tierDiscount);const min=tierMin.trim()?toCents(tierMin):discount===null?null:discount*3;
  const limit=Number(tierLimit);
  if(discount===null||discount<100||discount>1_000_000){setError("O desconto vai de R$ 1,00 a R$ 10.000,00.");return;}
  if(min===null||min<discount){setError("O pedido mínimo precisa ser igual ou maior que o desconto.");return;}
  if(!Number.isInteger(limit)||limit<1||limit>100000){setError("O limite de trocas vai de 1 a 100.000.");return;}
  setBusy(true);setError("");setMessage("");
  try{
   await merchantApi.saveDiscountRewardDraft(tenantId,{title:`${moneyShort(discount).replace(/\s/g," ")} de desconto`,points_cost:discount/POINT_CENTS,
    discount_cents:discount,min_order_cents:min,max_redemptions:limit});
   setMessage("Faixa criada como rascunho. Publique para aparecer no Meu Clube.");
   setTierOpen(false);setTierDiscount("10,00");setTierMin("");setTierLimit("1000");setRefresh(v=>v+1);
  }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível criar a faixa.");}
  finally{setBusy(false);}
 };
 const publish=async(item:DiscountRewardDraft,published:boolean)=>{
  if(busy||!canEdit)return;setBusy(true);setError("");setMessage("");
  try{
   await merchantApi.setRewardCatalogPublication(tenantId,item.id,published);
   setMessage(published?"Faixa publicada no Meu Clube. A troca de pontos continua desligada até a liberação.":"Faixa despublicada. Ela saiu do Meu Clube.");
   setConfirm(null);setRefresh(v=>v+1);
  }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível atualizar a publicação.");}
  finally{setBusy(false);}
 };
 const remove=async(item:DiscountRewardDraft)=>{
  if(busy||!canEdit)return;setBusy(true);setError("");setMessage("");
  try{await merchantApi.deleteDiscountRewardDraft(tenantId,item.id);setMessage("Faixa excluída.");setConfirm(null);setRefresh(v=>v+1);}
  catch(e){setError(e instanceof ApiError?e.message:"Não foi possível excluir.");}
  finally{setBusy(false);}
 };
 const clubUrl=window.location.origin+"/clube/"+encodeURIComponent(storeSlug);
 const joinUrl=window.location.origin+"/participar/"+encodeURIComponent(storeSlug);
 const copy=async()=>{try{await navigator.clipboard.writeText(joinUrl);setCopied(true);window.setTimeout(()=>setCopied(false),2000);}
  catch{setError("Não foi possível copiar. Selecione o endereço e copie manualmente.");}};
 const spendFor=(points:number)=>rule?Math.ceil(points*rule.per_cents/rule.points):null;
 const sortedRewards=[...rewards].sort((a,b)=>a.points_cost-b.points_cost);

 return <section className="vf-screen vf-program-page" aria-labelledby="vf-club-title">
  <div className="vf-head">
   <div><span className="vf-eyebrow">Meu clube</span><h1 id="vf-club-title" className="vf-h1">Como seu clube funciona</h1></div>
   <a className="vf-btn" href={clubUrl} target="_blank" rel="noopener noreferrer"><ExternalLink size={16}/> Prévia do Meu Clube</a>
  </div>
  <div className="vf-tabs" role="tablist" aria-label="Áreas do clube">
   {([["ganhar","1. Como ganhar"],["usar","2. Como usar"],["participar","3. Quem participa"],["testar","Testar"]] as [Tab,string][]).map(([key,label])=>
    <button key={key} type="button" role="tab" aria-selected={tab===key} className={"vf-tab"+(tab===key?" is-on":"")}
     onClick={()=>{setTab(key);setError("");setMessage("");setConfirm(null);}}>{label}</button>)}
  </div>
  {error&&<div className="vf-toast is-error" role="alert"><X size={18}/>{error}</div>}
  {message&&<div className="vf-toast" role="status"><Check size={18}/>{message}</div>}
  {!canEdit&&tab!=="participar"&&<div className="vf-toast is-info">Esta conta pode consultar o clube. Um administrador altera regras e recompensas.</div>}

  {tab==="ganhar"&&canEdit&&(loading?<p className="vf-muted" role="status">Carregando a regra…</p>:<div className="vf-grid2 vf-club-tab">
   <section className="vf-card" aria-labelledby="vf-earn-title">
    <div className="vf-card-head"><div><h2 id="vf-earn-title" className="vf-h2">Quanto devolver ao cliente?</h2>
     <span className="vf-muted vf-small">Uma decisão só. O sistema calcula pontos, trocas e custo.</span></div>
     <span className={"vf-chip "+(rule?"is-ok":"is-gold")}>{rule?(dirty?"Alterações não salvas":"Regra salva"):"Ainda não salva"}</span></div>
    <div className="vf-pills" role="group" aria-label="Porcentagem devolvida">
     {pctOptions.map(v=><button key={v} type="button" className={"vf-pill"+(draftPct===v?" is-on":"")} aria-pressed={draftPct===v}
      onClick={()=>setDraftPct(v)}>{pct(v)}</button>)}
    </div>
    <h3 className="vf-h3">Quando os pontos liberam?</h3>
    <div className="vf-pills" role="group" aria-label="Carência">
     {holdOptions.map(([d,l])=><button key={d} type="button" className={"vf-pill"+(hold===d?" is-on":"")} aria-pressed={hold===d} onClick={()=>setHold(d)}>{l}</button>)}
    </div>
    <span className="vf-muted vf-small">7 dias cobre o direito de arrependimento das compras online.</span>
    <h3 className="vf-h3">Por quanto tempo valem?</h3>
    <div className="vf-pills" role="group" aria-label="Validade">
     {validityOptions.map(([d,l])=><button key={d} type="button" className={"vf-pill"+(validity===d?" is-on":"")} aria-pressed={validity===d} onClick={()=>setValidity(d)}>{l}</button>)}
    </div>
    <div className="vf-club-actions"><button type="button" className="vf-btn is-primary" disabled={busy||!dirty} onClick={()=>void saveRule()}>{busy?"Salvando…":"Salvar regra"}</button></div>
   </section>
   <section className="vf-card is-soft" aria-labelledby="vf-understand">
    <span id="vf-understand" className="vf-eyebrow">O que o cliente entende</span>
    <p className="vf-club-sentence">A cada compra, o cliente recebe {pct(p)} de volta em pontos. Cada ponto vale R$ 0,01,
     {hold===0?" libera na hora":` libera em ${period(hold)}`} e vale por {period(validity)}.</p>
    <div className="vf-card vf-club-example">
     <span className="vf-ico tone-gold" aria-hidden="true"><ShoppingBag size={20}/></span>
     <div><span className="vf-muted vf-small">Compra de R$ 100,00</span>
      <strong>{examplePoints.toLocaleString("pt-BR")} pontos = {money(examplePoints*POINT_CENTS)}</strong></div>
    </div>
    <div className="vf-club-cost"><span className="vf-muted vf-small"><b>Custo para a loja</b></span>
     <div className="vf-bar" aria-hidden="true"><span style={{width:Math.min(100,p*10)+"%"}}/></div>
     <span className="vf-muted vf-small">Até {pct(p)} do valor das compras dos membros, só quando o cliente troca os pontos.</span></div>
    {summary.warnings.some(w=>w.key==="inconsistent_value")&&<p className="vf-note"><AlertTriangle size={16}/>
     Há recompensas antigas com outro valor de ponto. Revise em "Como usar" para o cliente entender o saldo.</p>}
   </section>
  </div>)}

  {tab==="usar"&&canEdit&&<div className="vf-club-tab">
   <div className="vf-card-head"><span className="vf-muted">Faixas de troca: o desconto sai do preço do ponto (1 ponto = R$ 0,01), sem conta manual.</span>
    {!tierOpen&&<button type="button" className="vf-btn is-primary" onClick={()=>{setTierOpen(true);setError("");setMessage("");}}><Plus size={17}/> Nova faixa</button>}</div>
   {tierOpen&&<form className="vf-card is-focus" onSubmit={createTier} aria-labelledby="vf-tier-title">
    <div className="vf-card-head"><h2 id="vf-tier-title" className="vf-h2">Nova faixa de troca</h2></div>
    <div className="vf-pills" role="group" aria-label="Valor do desconto">
     {DISCOUNTS.map(v=><button key={v} type="button" className={"vf-pill"+(toCents(tierDiscount)===v?" is-on":"")} aria-pressed={toCents(tierDiscount)===v}
      onClick={()=>setTierDiscount((v/100).toFixed(2).replace(".",","))}>{moneyShort(v)}</button>)}
    </div>
    <div className="vf-grid3">
     <label className="vf-field is-compact">Desconto (R$)<input inputMode="decimal" value={tierDiscount} onChange={e=>setTierDiscount(e.target.value)}/></label>
     <label className="vf-field is-compact">Pedido mínimo (R$)<input inputMode="decimal" placeholder={toCents(tierDiscount)?((toCents(tierDiscount)!*3)/100).toFixed(2).replace(".",","):""}
      value={tierMin} onChange={e=>setTierMin(e.target.value)}/><small>Se ficar vazio, usamos 3× o desconto.</small></label>
     <label className="vf-field is-compact">Limite de trocas<input inputMode="numeric" value={tierLimit} onChange={e=>setTierLimit(e.target.value)}/></label>
    </div>
    {toCents(tierDiscount)!==null&&<p className="vf-note">O cliente troca <b>{(toCents(tierDiscount)!/POINT_CENTS).toLocaleString("pt-BR")} pontos</b> por {money(toCents(tierDiscount)!)}
     {spendFor(toCents(tierDiscount)!/POINT_CENTS)?` — cerca de ${money(spendFor(toCents(tierDiscount)!/POINT_CENTS)!)} em compras`:""}.</p>}
    <div className="vf-club-actions"><button type="button" className="vf-btn" onClick={()=>setTierOpen(false)}>Cancelar</button>
     <button type="submit" className="vf-btn is-primary" disabled={busy}>{busy?"Criando…":"Criar faixa"}</button></div>
   </form>}
   {loading?<p className="vf-muted" role="status">Carregando faixas…</p>
    :sortedRewards.length===0?<div className="vf-card"><div className="vf-empty"><strong className="vf-h3">Nenhuma faixa ainda</strong>
      <p>Sem faixa de troca, os pontos não têm uso para o cliente. Comece por R$ 10 de desconto.</p></div></div>
    :<div className="vf-grid4">{sortedRewards.map(item=>{
      const value=item.discount_cents*100/item.points_cost; // centésimos de centavo por ponto
      const offPrice=Math.abs(value-POINT_CENTS*100)>1;
      const spend=spendFor(item.points_cost);
      return <article key={item.id} className="vf-card is-lift vf-tier">
       <div className="vf-tier-tags"><span className={"vf-chip "+(item.published?"is-ok":"is-soft")}>{item.published?"Publicada":"Rascunho"}</span>
        {offPrice&&<span className="vf-chip is-gold" title="Esta faixa usa outro valor de ponto">Outro preço</span>}</div>
       <strong className="vf-tier-reward">{moneyShort(item.discount_cents)}</strong>
       <span className="vf-tier-points">{item.points_cost.toLocaleString("pt-BR")} pontos</span>
       <span className="vf-muted vf-small">{spend?`≈ ${money(spend)} em compras · `:""}pedido mín. {moneyShort(item.min_order_cents)}</span>
       {confirm?.id===item.id?<div className="vf-tier-confirm">
         <span className="vf-small">{confirm.kind==="publish"?"Publicar no Meu Clube?":"Excluir esta faixa?"}</span>
         <div className="vf-pills"><button type="button" className="vf-btn is-small" onClick={()=>setConfirm(null)}>Não</button>
          <button type="button" className={"vf-btn is-small "+(confirm.kind==="delete"?"is-danger":"is-primary")} disabled={busy}
           onClick={()=>void(confirm.kind==="publish"?publish(item,true):remove(item))}>{confirm.kind==="publish"?"Publicar":"Excluir"}</button></div>
        </div>
       :<div className="vf-pills">
         {item.published?<button type="button" className="vf-btn is-small" disabled={busy} onClick={()=>void publish(item,false)}>Despublicar</button>
          :<><button type="button" className="vf-btn is-small is-primary" onClick={()=>setConfirm({id:item.id,kind:"publish"})}>Publicar</button>
           <button type="button" className="vf-btn is-small" aria-label={"Excluir "+item.title} onClick={()=>setConfirm({id:item.id,kind:"delete"})}><Trash2 size={15}/></button></>}
        </div>}
      </article>;})}</div>}
   <p className="vf-muted vf-small">Publicar mostra a faixa no Meu Clube. A troca por cupom só liga quando os pontos forem liberados para a loja.</p>
  </div>}

  {tab==="participar"&&<div className="vf-club-tab">
   <div className="vf-grid3">
    <article className="vf-card is-lift"><span className="vf-ico tone-purple" aria-hidden="true"><Link2 size={20}/></span>
     <strong className="vf-h3">Link de convite</strong><span className="vf-muted vf-small">Para o Instagram, o WhatsApp e a loja online.</span>
     <button type="button" className="vf-btn is-small vf-self-start" onClick={()=>void copy()}><Copy size={15}/>{copied?"Link copiado":"Copiar link"}</button></article>
    <article className="vf-card is-lift"><span className="vf-ico tone-gold" aria-hidden="true"><Smartphone size={20}/></span>
     <strong className="vf-h3">Cadastro pelo celular</strong><span className="vf-muted vf-small">O cliente entra no clube sozinho, sem o vendedor digitar.</span>
     <a className="vf-btn is-small vf-self-start" href={joinUrl} target="_blank" rel="noopener noreferrer"><ExternalLink size={15}/> Abrir cadastro</a></article>
    <article className="vf-card is-lift"><span className="vf-ico tone-green" aria-hidden="true"><Check size={20}/></span>
     <strong className="vf-h3">Quem já entrou</strong><span className="vf-muted vf-small">Saldo, contato e situação de cada participante.</span>
     <button type="button" className="vf-btn is-small vf-self-start" onClick={onViewClients}>Ver clientes</button></article>
   </div>
   <div className="vf-card vf-club-enroll"><EnrollmentManagement tenantId={tenantId} role={role} storeSlug={storeSlug} tenantStatus={tenantStatus}/></div>
  </div>}

  {tab==="testar"&&<div className="vf-card vf-club-tab" aria-label="Ferramentas de homologação">
   <div className="vf-card-head"><div><h2 className="vf-h2">Testar antes de ativar</h2>
    <span className="vf-muted vf-small">Simule pontos e trocas sem gerar saldo nem cupom de verdade.</span></div>
    <span className="vf-ico tone-purple" aria-hidden="true"><FlaskConical size={20}/></span></div>
   <LoyaltyTrialPanel tenantId={tenantId} ruleRefresh={refresh} rewardsRefresh={refresh}/>
  </div>}
 </section>;
}
