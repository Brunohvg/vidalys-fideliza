import {useEffect,useRef,useState} from "react";
import {CheckCircle2,Clock3,RefreshCw,Search,ShieldCheck,ShoppingBag,X} from "lucide-react";
import {ApiError,merchantApi,type PaidOrderInspection,type RecentOrdersPreview} from "./api";
import {reasons} from "./PaidOrderCheck";
import "./nuvemshop-orders-feed.css";

/* Pedidos da Nuvemshop na tela de Vendas: só leitura. Cada linha mostra o
   pedido, o valor, o pagamento informado pela loja e o que falta para virar
   pontos. Se a aba for aberta de novo em poucos segundos, o servidor devolve
   a última lista (a loja só é consultada a cada 20 s). */

const brl=(cents:number,currency:string)=>currency!=="BRL"?currency+" "+(cents/100).toFixed(2)
  :new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(cents/100);
const when=(iso:string|null)=>iso?new Date(iso).toLocaleDateString("pt-BR",{day:"2-digit",month:"short"}):"";
const PAY:Record<string,{label:string;tone:string}>={
  paid:{label:"Pago",tone:"is-ok"},authorized:{label:"Autorizado",tone:"is-soft"},pending:{label:"Pendente",tone:"is-gold"},
  partially_paid:{label:"Pago em parte",tone:"is-gold"},refunded:{label:"Estornado",tone:"is-danger"},
  partially_refunded:{label:"Estorno parcial",tone:"is-danger"},voided:{label:"Cancelado",tone:"is-danger"},
  abandoned:{label:"Abandonado",tone:"is-soft"},expired:{label:"Expirado",tone:"is-soft"},chargeback:{label:"Contestado",tone:"is-danger"},
};
const guidance=(err:unknown)=>{
  if(err instanceof ApiError){
    if(err.status===409)return "A loja ainda não autorizou a leitura de pedidos. Em Configurações → Canais de venda, clique em “Verificar acesso à Nuvemshop” e autorize de novo se for pedido.";
    if(err.status===429)return "A loja acabou de ser consultada. Atualizando em instantes…";
    if(err.status===403)return "Somente proprietário ou administrador pode consultar pedidos.";
    if(err.status===503)return "A integração com a Nuvemshop está indisponível no servidor. Confira as credenciais no Coolify.";
    if(err.status===502)return "A Nuvemshop não respondeu como esperado. Tente atualizar em alguns segundos.";
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
  const [checkedAt,setCheckedAt]=useState<Date|null>(null);
  const retried=useRef(false);

  useEffect(()=>{
    let active=true;let timer=0;
    setBusy(true);setError("");setSelected(null);
    merchantApi.recentNuvemshopOrders(tenantId).then(value=>{
      if(!active)return;
      setResponse(value);setCheckedAt(new Date());retried.current=false;
    }).catch(err=>{
      if(!active)return;
      setError(guidance(err));
      // Consulta recente: tenta de novo sozinho uma vez, depois do intervalo.
      if(err instanceof ApiError&&err.status===429&&!retried.current){
        retried.current=true;timer=window.setTimeout(()=>setRevision(v=>v+1),21000);
      }
    }).finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;window.clearTimeout(timer);};
  },[tenantId,revision]);

  const inspect=async(order:PaidOrderInspection)=>{
    if(checking)return;
    setChecking(order.order_id);setSelected(null);setCheckError("");
    try{setSelected(await merchantApi.inspectPaidOrder(tenantId,order.order_id));}
    catch(err){setCheckError(guidance(err));}
    finally{setChecking(null);}
  };
  const items=response?.items||[];

  return <section className="vf-orders" aria-label="Pedidos recentes da Nuvemshop">
    <div className="vf-orders-bar">
      <span className="vf-muted vf-small">{busy?"Consultando a loja…":checkedAt?"Atualizado às "+checkedAt.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})+" · últimos 10 pedidos":""}</span>
      <button type="button" className="vf-btn is-small" disabled={busy||!!checking} onClick={()=>{retried.current=false;setRevision(v=>v+1);}}
        aria-label="Atualizar pedidos da Nuvemshop"><RefreshCw size={16} className={busy?"vf-spin":""}/> {busy?"Consultando…":"Atualizar"}</button>
    </div>

    {busy&&!response&&<ul className="vf-orders-list is-loading" aria-hidden="true">{[0,1,2].map(i=><li key={i}><span/><span/><span/></li>)}</ul>}
    {!busy&&error&&<div className="vf-orders-msg" role="status"><ShieldCheck size={20} aria-hidden="true"/><span>{error}</span></div>}
    {!busy&&!error&&response&&items.length===0&&<div className="vf-orders-msg" role="status"><ShoppingBag size={20} aria-hidden="true"/>
      <span>Nenhum pedido retornado nesta página da loja.</span></div>}

    {items.length>0&&<ul className="vf-orders-list" aria-label="Pedidos retornados pela Nuvemshop">
      {items.map(order=>{const pay=PAY[order.payment_status]||{label:"Em análise",tone:"is-soft"};
        const review=reasons[order.review_status]?.label||"Conferência necessária";
        return <li key={order.order_id}>
          <span className="vf-orders-ico" aria-hidden="true"><ShoppingBag size={18}/></span>
          <div className="vf-orders-main">
            <strong>{order.order_number?"#"+order.order_number:"Pedido da loja"}</strong>
            <span>{when(order.paid_at)}{order.paid_at?" · ":""}{order.participant_verified?"Cliente do clube":"Cliente não identificado no clube"}</span>
          </div>
          <div className="vf-orders-value"><strong>{brl(order.reported_total_cents,order.currency)}</strong>
            <span className={"vf-chip "+pay.tone}>{pay.label}</span></div>
          <div className="vf-orders-review"><span>{review}</span></div>
          <button type="button" className="vf-btn is-small" disabled={!!checking} onClick={()=>void inspect(order)}>
            <Search size={15}/> {checking===order.order_id?"Conferindo…":"Conferir"}</button>
        </li>;})}
    </ul>}

    {checkError&&<div className="vf-orders-msg is-error" role="alert"><X size={18} aria-hidden="true"/><span>{checkError}</span></div>}
    {selected&&<div className="vf-orders-check" role="region" aria-label="Conferência atualizada do pedido">
      <CheckCircle2 size={22} aria-hidden="true"/>
      <div>
        <strong>{selected.order_number?"#"+selected.order_number:"Pedido ID "+selected.order_id} · {reasons[selected.review_status]?.label||"Conferência necessária"}</strong>
        <p>{reasons[selected.review_status]?.message}</p>
        <p className="vf-muted">{reasons[selected.review_status]?.next}</p>
        <small>Consulta sem gravação de pedidos, cupons ou pontos.</small>
      </div>
      <button type="button" className="vf-btn is-small" onClick={()=>setSelected(null)}>Fechar</button>
    </div>}

    {items.length>0&&<p className="vf-orders-note"><Clock3 size={15} aria-hidden="true"/>
      O pagamento é o informado pela Nuvemshop, não um comprovante bancário. Pedidos pagos ainda não geram pontos automaticamente.</p>}
  </section>;
}
