import {useEffect, useState, type FormEvent} from "react";
import {Banknote, ClipboardCheck, FileCheck2, RefreshCw, Search, ShieldCheck, ShoppingBag, UsersRound} from "lucide-react";
import {ApiError, merchantApi, type ManualSaleRecord, type ProgramParticipant, type Store} from "./api";
import "./sales-workspace.css";

const money=(cents:number)=>new Intl.NumberFormat("pt-BR",{
  style:"currency",currency:"BRL",
}).format(cents/100);
const localNow=()=>new Date(Date.now()-new Date().getTimezoneOffset()*60000)
  .toISOString().slice(0,19);
const numberFromMoney=(amount:string):number|null=>{
  const clean=amount.trim();
  if(!/^\d{1,7}(?:[,.]\d{1,2})?$/.test(clean))return null;
  const [whole,decimal=""]=clean.replace(",",".").split(".");
  const value=Number(whole)*100+Number(decimal.padEnd(2,"0"));
  return Number.isSafeInteger(value)&&value>0&&value<=100_000_000?value:null;
};
const label:Record<ManualSaleRecord["state"],string>={
  awaiting_member:"Cliente fora do clube",
  awaiting_review:"Aguardando conferência",
  verified_manual:"Conferência concluída",
  rejected:"Registro rejeitado",
};

export default function SalesWorkspace({tenantId,role}:{tenantId:string;role:Store["role"]}){
  const [items,setItems]=useState<ManualSaleRecord[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [version,setVersion]=useState(0);
  const [reference,setReference]=useState("");
  const [amount,setAmount]=useState("");
  const [paidAt,setPaidAt]=useState(localNow);
  const [evidence,setEvidence]=useState("");
  const [personQuery,setPersonQuery]=useState("");
  const [people,setPeople]=useState<ProgramParticipant[]>([]);
  const [selected,setSelected]=useState("");
  const [reviewing,setReviewing]=useState<ManualSaleRecord|null>(null);
  const [reviewNote,setReviewNote]=useState("");
  const canEdit=role==="owner"||role==="admin";

  useEffect(()=>{
    let active=true;
    setLoading(true);
    merchantApi.listManualSales(tenantId).then(data=>{
      if(active){setItems(data.items);setError("");}
    }).catch(cause=>{
      if(active)setError(cause instanceof ApiError?cause.message:"Falha ao consultar vendas.");
    }).finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  },[tenantId,version]);

  useEffect(()=>{
    if(!canEdit)return;
    let active=true;
    merchantApi.listParticipants(tenantId,{
      status:"active",q:personQuery.trim(),offset:0,
    }).then(data=>{
      if(active)setPeople(data.items);
    }).catch(()=>{if(active)setPeople([])});
    return()=>{active=false};
  },[tenantId,personQuery,canEdit]);

  const save=async(event:FormEvent)=>{
    event.preventDefault();if(busy||!canEdit)return;
    const cents=numberFromMoney(amount);
    const isoDate=paidAt?new Date(paidAt).toISOString():"";
    if(cents===null||!reference.trim()||!evidence.trim()||!paidAt){
      setError("Confira valor, referência, horário e comprovante da venda.");return;
    }
    setBusy(true);setError("");setMessage("");
    try{
      const result=await merchantApi.createManualSale(tenantId,{
        reference:reference.trim(),eligible_amount_cents:cents,
        participant_id:selected||null,reported_paid_at:isoDate,
        evidence_reference:evidence.trim(),
      });
      setMessage(result.already_recorded
        ?"Esta venda já estava registrada. Nenhum lançamento foi duplicado."
        :selected?"Venda registrada para conferência por outro administrador. Nenhum ponto foi creditado."
          :"Venda sem participante registrada como oportunidade. Nenhum ponto foi creditado.");
      setReference("");setAmount("");setEvidence("");setSelected("");
      setPaidAt(localNow());setVersion(v=>v+1);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Falha ao registrar a venda.");
    }finally{setBusy(false)}
  };

  const review=async(decision:"approve"|"reject")=>{
    if(!reviewing||busy)return;
    setBusy(true);setError("");setMessage("");
    try{
      await merchantApi.reviewManualSale(tenantId,reviewing.id,decision,reviewNote);
      setMessage(decision==="approve"
        ?"Conferência registrada. O motor de pontos continua desativado."
        :"Venda rejeitada. Nenhum ponto foi gerado.");
      setReviewing(null);setReviewNote("");setVersion(v=>v+1);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Falha ao conferir venda.");
    }finally{setBusy(false)}
  };

  return <div className="vf-sales-page">
    <section className="vf-sales-hero">
      <div><span className="portal-eyebrow"><ShoppingBag size={15}/> CANAL DE BALCÃO</span>
        <h2>Vendas registradas com segurança</h2>
        <p>A venda presencial é cadastrada aqui. O crédito de pontos dependerá de uma
          regra publicada e da verificação financeira no motor futuro.</p>
      </div>
      <span className="vf-sales-label"><ShieldCheck size={16}/> Sem crédito automático</span>
    </section>
    {error&&<div className="vf-sales-error" role="alert">{error}</div>}
    {message&&<div className="vf-sales-success" role="status">{message}</div>}
    {canEdit&&<section className="vf-sales-card">
      <div className="vf-sales-title"><Banknote size={21}/><div>
        <h3>Registrar venda do balcão</h3>
        <p>Use uma referência única do cupom ou recibo. Não informe CPF nem número de cartão.</p>
      </div></div>
      <form className="vf-sales-form" onSubmit={save}>
        <label>Referência da venda
          <input required value={reference} maxLength={80} placeholder="VENDA-00042"
            onChange={e=>setReference(e.target.value)} />
        </label>
        <label>Valor elegível (R$)
          <input required inputMode="decimal" value={amount} placeholder="100,00"
            onChange={e=>setAmount(e.target.value)} />
        </label>
        <label>Data e hora do pagamento informado
          <input required type="datetime-local" step={1} value={paidAt}
            onChange={e=>setPaidAt(e.target.value)} />
        </label>
        <label>Referência do comprovante
          <input required value={evidence} maxLength={80} placeholder="CUPOM-00042"
            onChange={e=>setEvidence(e.target.value)} />
        </label>
        <label className="vf-sales-wide">Buscar participante ativo
          <span className="vf-sales-search"><Search size={17}/>
            <input value={personQuery} maxLength={80} placeholder="Nome ou e-mail confirmado"
              onChange={e=>setPersonQuery(e.target.value)} />
          </span>
        </label>
        <label className="vf-sales-wide">Participante
          <select value={selected} onChange={e=>setSelected(e.target.value)}>
            <option value="">Não participa do programa — oportunidade de convite</option>
            {people.map(item=><option key={item.id} value={item.id}>
              {item.display_name||"Participante"} · {item.contact_email}
            </option>)}
            {selected&&!people.some(item=>item.id===selected)&&
              <option value={selected}>Participante selecionado anteriormente</option>}
          </select>
        </label>
        <div className="vf-sales-form-bottom">
          <p>Com participante: vai para conferência. Sem participante: registra apenas a oportunidade.
            Nenhuma venda altera o saldo neste estágio.</p>
          <button className="portal-primary" type="submit" disabled={busy}>
            <FileCheck2 size={17}/>{busy?"Registrando…":"Registrar para conferência"}
          </button>
        </div>
      </form>
    </section>}
    <section className="vf-sales-card">
      <div className="vf-sales-title"><ClipboardCheck size={21}/><div>
        <h3>Vendas recentes e conferências</h3>
        <p>Registros manuais desta loja. Somente outra pessoa com permissão administrativa pode conferir.</p>
      </div>
        <button className="vf-sales-refresh" type="button" onClick={()=>setVersion(v=>v+1)}>
          <RefreshCw size={16}/> Atualizar
        </button>
      </div>
      {loading?<p role="status">Carregando vendas…</p>:items.length===0?
        <div className="vf-sales-empty"><UsersRound size={27}/><strong>Nenhuma venda manual registrada</strong>
          <p>Quando houver vendas de balcão, você acompanhará a conferência aqui.</p>
        </div>:
        <div className="vf-sales-table-wrap"><table className="vf-sales-table"><thead><tr>
          <th>Venda</th><th>Participante</th><th>Valor</th><th>Conferência</th><th>Ação</th>
        </tr></thead><tbody>{items.map(item=><tr key={item.id}>
          <td><strong>{item.reference}</strong><small>{new Date(item.reported_paid_at).toLocaleString("pt-BR")}</small></td>
          <td>{item.participant_name||"Cliente não participante"}</td>
          <td><strong>{money(item.eligible_amount_cents)}</strong></td>
          <td>{label[item.state]}<small>0 ponto concedido nesta etapa</small></td>
          <td>{item.state==="awaiting_review"&&!item.submitted_by_me&&canEdit?
            <button className="vf-sales-refresh" type="button" onClick={()=>{
              setReviewing(item);setReviewNote("");
            }}>Conferir</button>:
            <span>{item.submitted_by_me&&item.state==="awaiting_review"
              ?"Outro administrador revisa":"—"}</span>}
          </td>
        </tr>)}</tbody></table></div>}
    </section>
    {reviewing&&<section className="vf-sales-card" aria-label="Conferência de venda">
      <div className="vf-sales-title"><ShieldCheck size={21}/><div>
        <h3>Conferir {reviewing.reference}</h3>
        <p>Compare o comprovante {reviewing.evidence_reference} com a venda de
          {money(reviewing.eligible_amount_cents)}. A aprovação não cria pontos.</p>
      </div></div>
      <label className="vf-sales-review-note">Observação da conferência
        <textarea required minLength={10} maxLength={240} rows={3}
          value={reviewNote} onChange={e=>setReviewNote(e.target.value)}
          placeholder="Descreva como conferiu o cupom e o pagamento." />
      </label>
      <div className="vf-sales-review-actions">
        <button type="button" className="vf-sales-refresh" onClick={()=>setReviewing(null)}>Cancelar</button>
        <button type="button" className="vf-sales-refresh" disabled={busy||reviewNote.trim().length<10}
          onClick={()=>void review("reject")}>Rejeitar</button>
        <button type="button" className="portal-primary" disabled={busy||reviewNote.trim().length<10}
          onClick={()=>void review("approve")}>Confirmar conferência</button>
      </div>
    </section>}
  </div>;
}
