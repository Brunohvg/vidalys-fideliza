import {useEffect,useState,type FormEvent} from "react";
import {ArrowRight,Gift,LockKeyhole,Plus,ShieldCheck,TicketPercent,Pencil,Trash2,X} from "lucide-react";
import {
  ApiError,merchantApi,type DiscountRewardDraft,type PointRuleDraft,type Store,
} from "./api";
import {estimateReward} from "./reward-economics";
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
  const [editingId,setEditingId]=useState<string|null>(null);
  const [deleteConfirmId,setDeleteConfirmId]=useState<string|null>(null);
  const [pointRule,setPointRule]=useState<PointRuleDraft|null>(null);
  const [ruleLoadError,setRuleLoadError]=useState(false);
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

  useEffect(()=>{
    let active=true;
    setPointRule(null);setRuleLoadError(false);
    merchantApi.getPointRuleDraft(tenantId).then(result=>{
      if(active)setPointRule(result.rule);
    }).catch(()=>{if(active)setRuleLoadError(true)});
    return()=>{active=false};
  },[tenantId]);

  const preview=estimateReward(Number(points),toCents(discount)??NaN,Number(limit),pointRule);
  const percent=(bps:number)=>(bps/100).toLocaleString("pt-BR",{
    maximumFractionDigits:2,
  })+"%";

  const reset=()=>{
    setEditingId(null);setDeleteConfirmId(null);
    setTitle("");setPoints("200");setDiscount("5,00");
    setMinOrder("30,00");setLimit("50");setAdvanced(false);
  };
  const edit=(item:DiscountRewardDraft)=>{
    setDeleteConfirmId(null);setEditingId(item.id);
    setTitle(item.title);setPoints(String(item.points_cost));
    setDiscount((item.discount_cents/100).toFixed(2).replace(".",","));
    setMinOrder((item.min_order_cents/100).toFixed(2).replace(".",","));
    setLimit(String(item.max_redemptions));setAdvanced(true);setError("");setMessage("");
  };
  const remove=async(item:DiscountRewardDraft)=>{
    if(busy||!canEdit||deleteConfirmId!==item.id)return;
    setBusy(true);setError("");setMessage("");
    try{
      await merchantApi.deleteDiscountRewardDraft(tenantId,item.id);
      setDrafts(v=>v.filter(x=>x.id!==item.id));
      setDeleteConfirmId(null);
      if(editingId===item.id)reset();
      setMessage("Rascunho excluído. Nenhum cupom ou saldo foi alterado.");
    }catch(e){setError(e instanceof ApiError?e.message:"Não foi possível excluir.");}
    finally{setBusy(false);}
  };
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
      const payload={
        title:title.trim(),points_cost:cost,discount_cents:amount,
        min_order_cents:minimum,max_redemptions:max,
      };
      const r=editingId
        ?await merchantApi.updateDiscountRewardDraft(tenantId,editingId,payload)
        :await merchantApi.saveDiscountRewardDraft(tenantId,payload);
      setDrafts(v=>editingId?v.map(x=>x.id===editingId?r.reward:x):[r.reward,...v]);
      reset();
      setMessage("Rascunho salvo. Nenhum cupom foi criado.");
    }catch(e){
      setError(e instanceof ApiError?e.message:"Não foi possível salvar.");
    }finally{setBusy(false)}
  };
  return <section className="vf-benefit-panel" aria-labelledby="vf-benefit-title">
    <header className="vf-benefit-head">
      <span className="vf-benefit-icon"><Gift size={22}/></span>
      <div><span className="portal-eyebrow">PRÊMIOS DO CLUBE</span>
        <h2 id="vf-benefit-title">Recompensas do clube</h2>
        <p>Crie e gerencie os descontos do clube. A publicação será liberada após a validação do checkout.</p></div>
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
        </span>
      </div>
      <div className="vf-economics" aria-label="Conferência da recompensa planejada">
        <div className="vf-economics-head">
          <strong>Antes de oferecer este desconto</strong>
          <span>Estimativa, não publicada</span>
        </div>
        <div className="vf-economics-grid">
          <div>
            <span>Compras elegíveis para juntar os pontos</span>
            <strong>{preview?.eligibleSpendCents!==null&&preview?.eligibleSpendCents!==undefined
              ?money(preview.eligibleSpendCents):"—"}</strong>
          </div>
          <div>
            <span>Desconto equivalente</span>
            <strong>{preview?.benefitRateBps!==null&&preview?.benefitRateBps!==undefined
              ?percent(preview.benefitRateBps):"—"}</strong>
          </div>
          <div>
            <span>Descontos nominais até o limite de resgates</span>
            <strong>{preview?money(preview.nominalExposureCents):"—"}</strong>
          </div>
        </div>
        {!pointRule&&<p>{ruleLoadError
          ?"Não foi possível conferir a regra de pontos; a estimativa de compras está indisponível."
          :"Salve uma regra de pontos para estimar quanto o cliente precisará comprar."}</p>}
        {preview?.benefitRateBps!==null&&preview?.benefitRateBps!==undefined
          &&preview.benefitRateBps>=10000&&<p className="vf-economics-alert">
            O desconto é igual ou maior que as compras necessárias para acumular os pontos.
            Revise essa combinação antes de avançar.</p>}
        <p>O valor pressupõe saldo inicial zero, regra constante e todas as compras elegíveis.
          Não equivale ao desconto na próxima compra nem comprova lucro.
          Verifique custos, outras promoções e frete antes de publicar.</p>
      </div>
      <div className="vf-benefit-footer">
        <span><ShieldCheck size={17}/> Ainda não aparece como benefício resgatável no Meu Clube.</span>
        <button type="submit" disabled={busy}>
          <Plus size={17}/>{busy?"Salvando…":editingId?"Salvar alterações":"Criar rascunho"}
        </button>
      </div>
      {editingId&&<button type="button" className="vf-benefit-advanced" onClick={reset} disabled={busy}><X size={15}/> Cancelar edição</button>}
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
            <small>Limite nominal planejado: {money(item.discount_cents*item.max_redemptions)}</small>
            {canEdit&&<div className="vf-draft-actions">
              <button type="button" onClick={()=>edit(item)} disabled={busy}><Pencil size={15}/> Editar</button>
              {deleteConfirmId!==item.id&&<button type="button"
                onClick={()=>{setDeleteConfirmId(item.id);setError("");setMessage("");}}
                disabled={busy}><Trash2 size={15}/> Excluir</button>}
              <button type="button" disabled title="Publicação indisponível até a validação dos pontos e checkout"><LockKeyhole size={15}/> Publicar (em breve)</button>
            </div>}
            {canEdit&&deleteConfirmId===item.id&&<div className="vf-draft-confirm"
              role="group" aria-label="Confirmação de exclusão da recompensa">
              <p>Excluir “{item.title}”? Não é possível desfazer. Nenhum cupom será alterado.</p>
              <div className="vf-draft-confirm-actions">
                <button type="button" disabled={busy} onClick={()=>setDeleteConfirmId(null)}>
                  Cancelar exclusão</button>
                <button type="button" className="danger" disabled={busy}
                  onClick={()=>void remove(item)}><Trash2 size={15}/>
                  {busy?"Excluindo…":"Confirmar exclusão"}</button>
              </div>
            </div>}
          </article>)}
        </div>}
    </div>
  </section>;
}
