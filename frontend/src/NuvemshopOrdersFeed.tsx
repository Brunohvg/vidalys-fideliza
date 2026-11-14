import {useEffect,useState} from "react";
import {ArrowRight,Clock3,RefreshCw,Search,ShieldCheck,ShoppingBag} from "lucide-react";
import {ApiError,merchantApi,type PaidOrderInspection,type RecentOrdersPreview} from "./api";
import {reasons} from "./PaidOrderCheck";
import "./nuvemshop-orders-feed.css";

const brl=(cents:number,currency:string)=>{
  if(currency!=="BRL")return currency+" "+(cents/100).toFixed(2);
  return new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(cents/100);
};
const status=(value:string)=>{
  const labels:Record<string,string>={
    paid:"Pago na loja",pending:"Pendente",authorized:"Autorizado",
    partially_paid:"Pagamento parcial",refunded:"Estornado",
    partially_refunded:"Estorno parcial",voided:"Cancelado",
    abandoned:"Abandonado",
  };
  return labels[value]||"Em análise";
};
const guidance=(err:unknown)=>{
  if(err instanceof ApiError){
    if(err.status===409)return "A consulta automática precisa de read_orders autorizado e da prévia de pedidos habilitada. Confira Configurações.";
    if(err.status===429)return "Aguarde um momento antes de atualizar os pedidos.";
    if(err.status===403)return "Somente proprietário ou administrador pode consultar pedidos.";
  }
  return "Não foi possível carregar os pedidos da loja. Confira a conexão em Configurações.";
};

export default function NuvemshopOrdersFeed({tenantId}:{tenantId:string}){
  const [response,setResponse]=useState<RecentOrdersPreview|null>(null);
  const [busy,setBusy]=useState(true);
  const [revision,setRevision]=useState(0);
  const [error,setError]=useState("");
  const [selected,setSelected]=useState<PaidOrderInspection|null>(null);
  const [checking,setChecking]=useState<string|null>(null);
  const [checkError,setCheckError]=useState("");

  useEffect(()=>{
    let active=true;setBusy(true);setResponse(null);setError("");setSelected(null);
    merchantApi.recentNuvemshopOrders(tenantId).then(value=>{
      if(active)setResponse(value);
    }).catch(err=>{if(active)setError(guidance(err));})
      .finally(()=>{if(active)setBusy(false)});
    return()=>{active=false};
  },[tenantId,revision]);

  const inspect=async(order:PaidOrderInspection)=>{
    if(checking)return;
    setChecking(order.order_id);setSelected(null);setCheckError("");
    try{
      const value=await merchantApi.inspectPaidOrder(tenantId,order.order_id);
      setSelected(value);
    }catch(err){setCheckError(guidance(err));}
    finally{setChecking(null);}
  };

  return <section className="vf-online-feed" aria-label="Pedidos recentes da Nuvemshop">
    <header className="vf-online-feed-head">
      <div><span className="portal-eyebrow">DADOS DA NUVEMSHOP</span>
        <h4 id="vf-online-feed-title">Pedidos da loja</h4>
        <p>Primeira página retornada pela integração. Sem digitar números nem cadastrar as compras novamente.</p>
      </div>
      <button type="button" disabled={busy||!!checking}
        onClick={()=>setRevision(value=>value+1)} aria-label="Atualizar pedidos da Nuvemshop">
        <RefreshCw size={16}/>{busy?"Consultando…":"Atualizar"}</button>
    </header>
    {busy&&<p className="vf-online-feed-info" role="status">
      <Clock3 size={16}/> Consultando os pedidos autorizados…</p>}
    {!busy&&error&&<p className="vf-online-feed-info" role="status">
      <ShieldCheck size={17}/> {error}</p>}
    {!busy&&!error&&response?.items.length===0&&<p className="vf-online-feed-info">
      <ShoppingBag size={18}/> Nenhum pedido retornado nesta página da loja.</p>}
    {!busy&&!error&&!!response?.items.length&&<>
      <ul className="vf-online-feed-list" aria-label="Pedidos retornados pela Nuvemshop">
        {response.items.map(order=><li key={order.order_id}>
          <div className="vf-online-feed-main">
            <strong>{order.order_number?"#"+order.order_number:"Pedido da loja"}</strong>
            <small>ID interno {order.order_id}</small>
          </div>
          <div className="vf-online-feed-payment">
            <strong>{brl(order.reported_total_cents,order.currency)}</strong>
            <small>{status(order.payment_status)}</small>
          </div>
          <div className="vf-online-feed-status">
            <strong>{reasons[order.review_status]?.label||"Conferência necessária"}</strong>
            <small>{order.participant_verified?"Participante vinculado":"Participante não confirmado"}</small>
          </div>
          <button type="button" disabled={!!checking}
            onClick={()=>void inspect(order)}>
            <Search size={15}/>{checking===order.order_id?"Conferindo…":"Conferir"}
          </button>
        </li>)}
      </ul>
      <p className="vf-online-feed-note">
        <ShieldCheck size={16}/> A lista reflete o estado informado pela Nuvemshop,
        não comprovantes bancários. Mesmo pedidos pagos não geram pontos automaticamente nesta etapa.
      </p>
    </>}
    {checkError&&<p className="vf-online-feed-info" role="status">{checkError}</p>}
    {selected&&<div className="vf-online-feed-inspection" role="region"
      aria-label="Conferência atualizada do pedido">
      <div>
        <span className="portal-eyebrow">CONFERÊNCIA ATUALIZADA</span>
        <h4>{selected.order_number?"#"+selected.order_number:"Pedido ID "+selected.order_id}</h4>
        <strong>{reasons[selected.review_status]?.label||"Conferência necessária"}</strong>
        <p>{reasons[selected.review_status]?.message}</p>
        <p>{reasons[selected.review_status]?.next}</p>
        <small>Consulta sem gravação de pedidos, cupons ou pontos.</small>
      </div>
      <button type="button" onClick={()=>setSelected(null)}>
        Fechar <ArrowRight size={15}/>
      </button>
    </div>}
  </section>;
}
