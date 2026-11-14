import {useEffect,useState,type FormEvent} from "react";
import {BadgeCheck,ClipboardCheck,Info,LockKeyhole,Search,ShieldAlert,ShoppingBag} from "lucide-react";
import {ApiError,merchantApi,type PaidOrderInspection} from "./api";
import "./paid-order-check.css";

/** O pedido pode constar pago na loja sem prova de captura financeira no PSP. */
export const reasons:Record<PaidOrderInspection["review_status"],{
  label:string;message:string;next:string
}>={
  blocked_cancelled:{
    label:"Pedido cancelado",message:"O pedido está cancelado. Não gera pontos.",
    next:"Se for necessário revisar, confirme o cancelamento e seu estorno no provedor de pagamento.",
  },
  blocked_refund:{
    label:"Pagamento estornado",message:"Há estorno total ou parcial informado.",
    next:"Concilie o estorno antes de liberar qualquer saldo.",
  },
  not_paid:{
    label:"Aguardando pagamento",message:"O pedido ainda não consta integralmente pago.",
    next:"Aguarde a confirmação de pagamento; pedido criado não concede pontos.",
  },
  payment_date_missing:{
    label:"Data de pagamento ausente",message:"A loja não informou uma data de pagamento válida.",
    next:"Confira a transação na loja e no provedor financeiro.",
  },
  customer_not_verified:{
    label:"Cliente não vinculado",message:"O comprador não está vinculado como participante verificado do clube.",
    next:"Confirme o aceite e o vínculo do cliente antes de considerar pontuação.",
  },
  manual_payment_review:{
    label:"Pagamento manual exige conferência",
    message:"O status da loja não confirma captura independente no meio de pagamento.",
    next:"Confira o comprovante e o meio de recebimento antes de considerar crédito.",
  },
  reported_paid_amount_review:{
    label:"Valores divergentes",message:"Valor total e valor pago informado não coincidem.",
    next:"Confira descontos, ajustes, pagamentos parciais e o comprovante financeiro.",
  },
  reported_paid_requires_reconciliation:{
    label:"Falta conciliação financeira",
    message:"A loja informa pagamento, mas ainda falta verificar a captura no provedor.",
    next:"A integração com o provedor de pagamentos precisa confirmar valor e transação. Não conceda pontos pelo status sozinho.",
  },
};

const money=(cents:number,currency:string)=>{
  if(currency!=="BRL")return (cents/100).toFixed(2)+" "+currency;
  return new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(cents/100);
};

export default function PaidOrderCheck({tenantId}:{tenantId:string}){
  const [orderId,setOrderId]=useState("");
  const [result,setResult]=useState<PaidOrderInspection|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{setOrderId("");setResult(null);setError("");},[tenantId]);
  const valid=/^[1-9][0-9]{0,17}$/.test(orderId.trim());
  const check=async(event:FormEvent)=>{
    event.preventDefault();
    if(!valid||busy)return;
    setResult(null);setError("");setBusy(true);
    try{
      const response=await merchantApi.inspectPaidOrder(tenantId,orderId.trim());
      setResult(response);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível consultar o pedido agora.");
    }finally{setBusy(false);}
  };
  const status=result?reasons[result.review_status]:null;
  return <section className="vf-order-check" aria-labelledby="vf-order-check-title">
    <header className="vf-order-check-head">
      <ShoppingBag size={22}/>
      <div>
        <h3 id="vf-order-check-title">Conferir uma compra na Nuvemshop</h3>
        <p>Consulte o pedido real autorizado e veja por que ele ainda não pode gerar pontos. Sem alterar a loja.</p>
      </div>
    </header>
    <form className="vf-order-check-form" onSubmit={check}>
      <label htmlFor="vf-order-id">ID interno do pedido na Nuvemshop</label>
      <div>
        <input id="vf-order-id" value={orderId}
          onChange={event=>{setOrderId(event.target.value);setResult(null);setError("");}}
          inputMode="numeric" autoComplete="off" maxLength={18}
          placeholder="Ex.: 123456789" aria-invalid={orderId.length>0&&!valid}/>
        <button type="submit" disabled={!valid||busy}>
          <Search size={16}/>{busy?"Consultando…":"Conferir pedido"}</button>
      </div>
      <small>Use o ID numérico da URL administrativa do pedido, não o número público da compra.
        Requer a permissão de leitura de pedidos e a prévia ativada na integração.</small>
    </form>
    {error&&<div className="vf-order-check-error" role="alert">
      <Info size={17}/><p>{error} Confira a conexão e as permissões em Configurações.</p>
    </div>}
    {result&&status&&<div className="vf-order-check-result" role="region" aria-label="Resultado da conferência do pedido">
      <div className="vf-order-check-state">
        <ShieldAlert size={21}/>
        <div>
          <strong>{status.label}</strong>
          <p>{status.message}</p>
        </div>
      </div>
      <div className="vf-order-check-facts">
        <div><span>Pedido consultado</span><strong>#{result.order_id}</strong></div>
        <div><span>Pagamento na loja</span><strong>{result.payment_status==="paid"?"Pago":result.payment_status==="pending"?"Pendente":result.payment_status}</strong></div>
        <div><span>Valor registrado</span><strong>{money(result.reported_total_cents,result.currency)}</strong></div>
        <div><span>Participante identificado</span><strong>{result.participant_verified?"Vinculado":"Não comprovado"}</strong></div>
      </div>
      <div className="vf-order-check-next">
        <ClipboardCheck size={19}/><div><strong>O que falta fazer</strong><p>{status.next}</p></div>
      </div>
      <p className="vf-order-check-safety"><LockKeyhole size={15}/>
        Consulta somente leitura. Nenhum ponto foi criado, nenhum cupom foi emitido
        e o status “Pago” da plataforma não prova liquidação no provedor.
      </p>
    </div>}
    {!result&&!error&&<div className="vf-order-check-hint">
      <BadgeCheck size={16}/> Conferência real por pedido, sem conceder pontos antecipadamente.
    </div>}
  </section>;
}
