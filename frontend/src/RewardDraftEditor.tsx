import {useEffect,useState,type FormEvent} from "react";
import {ArrowRight,Gift,LockKeyhole,Plus,ShieldCheck,TicketPercent} from "lucide-react";
import {
  ApiError,merchantApi,type DiscountRewardDraft,type Store,
} from "./api";
import "./benefit-studio.css";

const toCents=(value:string):number|null=>{
  const match=/^(\d{1,7})(?:[,.](\d{1,2}))?$/.exec(value.trim());
  if(!match)return null;
  const cents=Number(match[1])*100+Number((match[2]||"").padEnd(2,"0"));
  return cents>=0&&cents<=100_000_000?cents:null;
};
const money=(value:number)=>new Intl.NumberFormat("pt-BR",{
  style:"currency",currency:"BRL",
}).format(value/100);

export default function RewardDraftEditor({tenantId,role}:{
  tenantId:string;role:Store["role"];
}){
  const [drafts,setDrafts]=useState<DiscountRewardDraft[]>([]);
  const [title,setTitle]=useState("");
  const [points,setPoints]=useState("200");
  const [discount,setDiscount]=useState("5,00");
  const [minOrder,setMinOrder]=useState("30,00");
  const [limit,setLimit]=useState("50");
  const [advanced,setAdvanced]=useState(false);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const canEdit=role==="owner"||role==="admin";

  useEffect(()=>{
    let active=true;setLoading(true);setError("");
    merchantApi.listDiscountRewardDrafts(tenantId).then(r=>{
      if(active)setDrafts(r.items);
    }).catch(e=>{
      if(active)setError(e instanceof ApiError?e.message:"Falha ao consultar recompensas.");
    }).finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  },[tenantId]);

  const save=async(event:FormEvent)=>{
    event.preventDefault();if(!canEdit||busy)return;
    const cost=Number(points),amount=toCents(discount),minimum=toCents(minOrder);
    const max=Number(limit);
    if(!title.trim()||!Number.isInteger(cost)||cost<1||cost>1_000_000
      ||amount===null||amount<100||amount>1_000_000
      ||minimum===null||minimum<amount
      ||!Number.isInteger(max)||max<1||max>100000){
      setError("Preencha um título, pontos e desconto válidos. O pedido mínimo deve cobrir o desconto.");
      return;
    }
    setBusy(true);setMessage("");setError("");
    try{
      const r=await merchantApi.saveDiscountRewardDraft(tenantId,{
        title:title.trim(),points_cost:cost,discount_cents:amount,
        min_order_cents:minimum,max_redemptions:max,
      });
      setDrafts(v=>[r.reward,...v]);
      setTitle("");
      setMessage("Recompensa guardada como rascunho. Nenhum cupom foi criado.");
    }catch(e){
      setError(e instanceof ApiError?e.message:"Não foi possível salvar.");
    }finally{setBusy(false)}
  };
  return <section className="vf-benefit-panel" aria-labelledby="vf-benefit-title">
    <header className="vf-benefit-head">
      <span className="vf-benefit-icon"><Gift size={22}/></span>
      <div><span className="portal-eyebrow">PRÊMIOS DO CLUBE</span>
        <h2 id="vf-benefit-title">O que o cliente pode conquistar?</h2>
        <p>Defina descontos que serão trocados por pontos quando o checkout estiver pronto.</p></div>
      <span className="vf-benefit-state"><LockKeyhole size={14}/> Apenas rascunho</span>
    </header>
    {error&&<p className="vf-benefit-error" role="alert">{error}</p>}
    {message&&<p className="vf-benefit-success" role="status">{message}</p>}
    {canEdit&&<form className="vf-benefit-form" onSubmit={save}>
      <label className="vf-benefit-wide">Nome da recompensa
        <input value={title} maxLength={100} required placeholder="Ex.: R$ 5 de desconto"
          onChange={e=>setTitle(e.target.value)}/>
      </label>
      <label>Pontos necessários
        <input value={points} type="number" min="1" max="1000000" step="1"
          onChange={e=>setPoints(e.target.value)}/>
      </label>
      <label>Valor do desconto (R$)
        <input value={discount} inputMode="decimal" placeholder="5,00"
          onChange={e=>setDiscount(e.target.value)}/>
      </label>
      <button className="vf-benefit-advanced" type="button" aria-expanded={advanced}
        onClick={()=>setAdvanced(v=>!v)}>
        {advanced?"Ocultar condições":"Condições e limites"} <ArrowRight size={15}/>
      </button>
      {advanced&&<>
        <label>Pedido mínimo (R$)
          <input value={minOrder} inputMode="decimal" onChange={e=>setMinOrder(e.target.value)}/>
        </label>
        <label>Quantidade máxima de resgates
          <input value={limit} min="1" max="100000" type="number" step="1"
            onChange={e=>setLimit(e.target.value)}/>
        </label>
      </>}
      <div className="vf-benefit-summary">
        <TicketPercent size={20}/><span>
          O cliente trocará <strong>{Number(points)||"—"} pontos</strong> por
          <strong> {toCents(discount)!==null?money(toCents(discount)!):"—"}</strong> na próxima compra.
          O limite não garante que a loja tenha margem suficiente: confira os custos antes de publicar.
        </span>
      </div>
      <div className="vf-benefit-footer">
        <span><ShieldCheck size={17}/> Ainda não aparece como benefício resgatável no Meu Clube.</span>
        <button type="submit" disabled={busy}>
          <Plus size={17}/>{busy?"Salvando…":"Guardar recompensa"}
        </button>
      </div>
    </form>}
    <div className="vf-benefit-saved">
      <h3>Recompensas planejadas</h3>
      {loading?<p role="status">Carregando rascunhos…</p>:
        drafts.length===0?<p>Nenhuma recompensa definida. Comece com um desconto simples.</p>:
        <div className="vf-benefit-grid">
          {drafts.map(item=><article className="vf-benefit-card" key={item.id}>
            <span><TicketPercent size={16}/> Não publicada</span>
            <h4>{item.title}</h4>
            <strong>{money(item.discount_cents)} de desconto</strong>
            <p>{item.points_cost.toLocaleString("pt-BR")} pontos ·
              Pedido mínimo {money(item.min_order_cents)}</p>
            <small>Sem cupom, sem resgate e sem consumo de pontos.</small>
          </article>)}
        </div>}
    </div>
  </section>;
}
