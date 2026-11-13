import {useMemo,useState} from "react";
import {Calculator,ShieldCheck,TicketPercent} from "lucide-react";
import type {CostItem} from "./api";
import "./benefit-studio.css";
const cents=(raw:string):number|null=>{
 const m=/^(\d{1,7})(?:[,.](\d{1,2}))?$/.exec(raw.trim());
 if(!m)return null;
 return Number(m[1])*100+Number((m[2]||"").padEnd(2,"0"));
};
const brl=(c:number)=>new Intl.NumberFormat("pt-BR",{
 style:"currency",currency:"BRL",
}).format(c/100);

export default function BenefitCostOverview({initialItem,onOpenProgram}:{
 initialItem?:CostItem|null;onOpenProgram:()=>void;
}){
 const [sale,setSale]=useState(initialItem?.selling_price_cents!=null
   ?(initialItem.selling_price_cents/100).toFixed(2).replace(".",","):"");
 const [reward,setReward]=useState("");
 const [uses,setUses]=useState("10");
 const [details,setDetails]=useState(false);
 const [cost,setCost]=useState(initialItem?.unit_cost_cents!=null?(initialItem.unit_cost_cents/100).toFixed(2).replace(".",","):"");
 const [taxes,setTaxes]=useState("");
 const [shipping,setShipping]=useState("");
 const [misc,setMisc]=useState("");
 const [marginOpen,setMarginOpen]=useState(false);
 const info=useMemo(()=>{
  const amount=cents(sale),discount=cents(reward),n=Number(uses);
  if(amount===null||discount===null||amount<=0||discount<=0||discount>=amount
   ||!Number.isInteger(n)||n<1||n>100000)return null;
  return {amount,discount,n,cost:discount*n};
 },[sale,reward,uses]);
 const expenses=[cost,taxes,shipping,misc].map(cents);
 const marginReady=marginOpen&&info!==null&&expenses.every(value=>value!==null);
 const marginValue=marginReady&&info?info.amount-info.discount-expenses.reduce<number>((sum,v)=>sum+(v??0),0):null;
 return <div className="vf-benefit-panel">
  <header className="vf-benefit-head">
   <span className="vf-benefit-icon"><Calculator size={23}/></span>
   <div><span className="portal-eyebrow">SIMULAÇÃO DO CLUBE</span>
    <h2>Quanto pode custar uma recompensa?</h2>
    <p>Entenda o valor dos descontos sem preencher uma planilha de custos.</p>
   </div>
  </header>
  {initialItem&&<p className="vf-benefit-success">
   Produto de referência: {initialItem.name}. O cálculo abaixo não confirma margem ou lucro.</p>}
  <div className="vf-benefit-form">
   <label>Valor da próxima compra (R$)
    <input aria-label="Valor da próxima compra" inputMode="decimal" placeholder="100,00"
     value={sale} onChange={e=>setSale(e.target.value)}/>
   </label>
   <label>Desconto por recompensa (R$)
    <input aria-label="Desconto por recompensa" inputMode="decimal" placeholder="5,00"
     value={reward} onChange={e=>setReward(e.target.value)}/>
   </label>
   <label>Quantidade máxima de resgates
    <input aria-label="Quantidade máxima de resgates" type="number" min={1} max={100000}
     value={uses} onChange={e=>setUses(e.target.value)}/>
   </label>
   <div className="vf-benefit-summary">
    <TicketPercent size={20}/>
    {info?<span>Em cada compra, o cliente pagaria <strong>{brl(info.amount-info.discount)}</strong>
      antes de outras taxas. Se {info.n} clientes utilizarem a recompensa, o valor nominal
      máximo dos descontos será <strong>{brl(info.cost)}</strong>.</span>
    :<span>Preencha o valor da compra, o desconto e a quantidade de resgates.
      O desconto deve ser menor que o valor da compra.</span>}
   </div>
   <button className="vf-benefit-advanced" type="button" aria-expanded={marginOpen}
    onClick={()=>setMarginOpen(v=>!v)}>{marginOpen?"Ocultar cálculo de margem":"Ver impacto na margem (opcional)"}</button>
   {marginOpen&&<>
    <p className="vf-benefit-wide" style={{fontSize:12,color:"#526e65",margin:0}}>Informe despesas da compra inteira, não apenas de um produto. Use zero somente quando a ausência do custo tiver sido confirmada.</p>
    <label>Custo total dos produtos (R$)<input aria-label="Custo total dos produtos" inputMode="decimal" value={cost} onChange={e=>setCost(e.target.value)} placeholder="Não informado"/></label>
    <label>Taxas e impostos (R$)<input aria-label="Taxas e impostos" inputMode="decimal" value={taxes} onChange={e=>setTaxes(e.target.value)} placeholder="Não informado"/></label>
    <label>Frete subsidiado pela loja (R$)<input aria-label="Frete subsidiado pela loja" inputMode="decimal" value={shipping} onChange={e=>setShipping(e.target.value)} placeholder="Não informado"/></label>
    <label>Outras despesas variáveis (R$)<input aria-label="Outras despesas variáveis" inputMode="decimal" value={misc} onChange={e=>setMisc(e.target.value)} placeholder="Não informado"/></label>
    <div className="vf-benefit-summary" role="status"><Calculator size={20}/><span>{marginValue===null
     ?"Contribuição indisponível: confira valor da compra, desconto e os quatro custos. Campo vazio não é zero."
     :<>Contribuição estimada após desconto: <strong>{brl(marginValue)}</strong> por compra.
     {marginValue<0?" Resultado negativo: revise a oferta.":""} Este cálculo não inclui custos fixos nem comprova lucro líquido.</>}</span></div>
   </>}
   <div className="vf-benefit-summary">
    <ShieldCheck size={20}/><span>
      <strong>Isso não é o lucro da loja.</strong> Sem custos dos produtos,
      impostos, taxas e frete, não podemos afirmar se a promoção é rentável.
      Nenhum desconto será ativado nesta simulação.
    </span>
   </div>
   <button className="vf-benefit-advanced" type="button"
    aria-expanded={details} onClick={()=>setDetails(v=>!v)}>
    {details?"Ocultar explicação":"O que significa essa estimativa?"}
   </button>
   {details&&<p className="vf-benefit-summary">
    O custo exibido é somente o desconto nominal máximo. Margem e recompra
    dependem dos dados reais de vendas e de todas as despesas. Os custos por
    SKU continuam como ferramenta avançada, sem obrigação de cadastro para iniciar o clube.
   </p>}
   <div className="vf-benefit-footer">
    <span>Planejamento somente. Não gera pontos nem cupons.</span>
    <button type="button" onClick={onOpenProgram}>
     <TicketPercent size={17}/> Configurar recompensas
    </button>
   </div>
  </div>
 </div>;
}
