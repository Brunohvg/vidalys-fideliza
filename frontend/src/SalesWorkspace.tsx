import {useEffect, useState, type FormEvent} from "react";
import {
  ArrowRight, CheckCircle2, ClipboardCheck, Clock3, FileText,
  Plus, RefreshCw, Search, ShieldCheck, ShoppingBag, UsersRound,
} from "lucide-react";
import {
  ApiError, merchantApi,
  type ManualSaleRecord, type ProgramParticipant, type Store,
} from "./api";
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

const receiptReference=(raw:string):string|null=>{
  const value=raw.normalize("NFKC").trim().toUpperCase().replace(/\s+/g,"-");
  const reference=/^\d{1,72}$/.test(value)?"CUPOM-"+value:value;
  return /^[A-Z0-9][A-Z0-9._/-]{3,79}$/.test(reference)?reference:null;
};

const statusText:Record<ManualSaleRecord["state"],string>={
  awaiting_member:"Sem participante",
  awaiting_review:"Aguardando conferência",
  verified_manual:"Conferida",
  rejected:"Rejeitada",
};

const statusClass:Record<ManualSaleRecord["state"],string>={
  awaiting_member:"vf-sale-state-muted",
  awaiting_review:"vf-sale-state-pending",
  verified_manual:"vf-sale-state-reviewed",
  rejected:"vf-sale-state-rejected",
};

export default function SalesWorkspace({tenantId,role}:{
  tenantId:string;role:Store["role"];
}){
  const [section,setSection]=useState<"new"|"history">("new");
  const [items,setItems]=useState<ManualSaleRecord[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [version,setVersion]=useState(0);

  const [receipt,setReceipt]=useState("");
  const [amount,setAmount]=useState("");
  const [paidAt,setPaidAt]=useState(localNow);
  const [customTime,setCustomTime]=useState(false);

  const [personQuery,setPersonQuery]=useState("");
  const [searchOpen,setSearchOpen]=useState(false);
  const [people,setPeople]=useState<ProgramParticipant[]>([]);
  const [peopleError,setPeopleError]=useState(false);
  const [selected,setSelected]=useState("__choose__");

  const [reviewing,setReviewing]=useState<ManualSaleRecord|null>(null);
  const [reviewNote,setReviewNote]=useState("");
  const canEdit=role==="owner"||role==="admin";

  useEffect(()=>{
    let active=true;
    setLoading(true);
    merchantApi.listManualSales(tenantId).then(data=>{
      if(active)setItems(data.items);
    }).catch(cause=>{
      if(active)setError(cause instanceof ApiError?cause.message:"Não foi possível consultar as vendas.");
    }).finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  },[tenantId,version]);

  useEffect(()=>{
    if(!canEdit)return;
    let active=true;
    setPeopleError(false);
    merchantApi.listParticipants(tenantId,{
      status:"active",q:personQuery.trim(),offset:0,
    }).then(data=>{
      if(active)setPeople(data.items);
    }).catch(()=>{
      if(active){setPeople([]);setPeopleError(true);}
    });
    return()=>{active=false};
  },[tenantId,personQuery,canEdit]);

  const openSection=(next:"new"|"history")=>{
    setSection(next);setError("");setMessage("");setReviewing(null);
  };

  const save=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy||!canEdit)return;
    const cents=numberFromMoney(amount);
    const reference=receiptReference(receipt);
    const chosen=selected==="__choose__"?null:selected;
    const selectedTime=customTime?new Date(paidAt):new Date();
    if(selected==="__choose__"){
      setError("Selecione um participante ou marque que o cliente ainda não participa.");
      return;
    }
    if(cents===null||!reference){
      setError("Confira o valor e o número do cupom ou recibo.");
      return;
    }
    if(Number.isNaN(selectedTime.getTime())){
      setError("Informe uma data de venda válida.");
      return;
    }
    setBusy(true);setError("");setMessage("");
    try{
      const result=await merchantApi.createManualSale(tenantId,{
        reference,eligible_amount_cents:cents,
        participant_id:chosen||null,reported_paid_at:selectedTime.toISOString(),
        evidence_reference:reference,
      });
      setMessage(result.already_recorded
        ?"Este cupom já estava registrado. Não criamos outra venda."
        :chosen
          ?"Venda registrada. Outro administrador poderá conferir o comprovante. Nenhum ponto foi creditado."
          :"Venda registrada sem participante. Nenhum ponto foi creditado.");
      setReceipt("");setAmount("");setSelected("__choose__");
      setPaidAt(localNow());setCustomTime(false);
      setPersonQuery("");setSearchOpen(false);setVersion(v=>v+1);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível registrar a venda.");
    }finally{setBusy(false)}
  };

  const review=async(decision:"approve"|"reject")=>{
    if(!reviewing||busy)return;
    setBusy(true);setError("");setMessage("");
    try{
      await merchantApi.reviewManualSale(
        tenantId,reviewing.id,decision,reviewNote,
      );
      setMessage(decision==="approve"
        ?"Conferência registrada. Nenhum ponto foi creditado."
        :"Venda rejeitada. Nenhum ponto foi creditado.");
      setReviewing(null);setReviewNote("");setVersion(v=>v+1);
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Não foi possível concluir a conferência.");
    }finally{setBusy(false)}
  };

  const pending=items.filter(item=>item.state==="awaiting_review").length;

  return <div className="vf-sales-page">
    <header className="vf-sale-intro">
      <div className="vf-sale-intro-icon" aria-hidden="true"><ShoppingBag size={24}/></div>
      <div>
        <span className="portal-eyebrow">VENDAS PRESENCIAIS</span>
        <h2>Venda registrada em poucos passos.</h2>
        <p>Associe o cliente ao clube e guarde o comprovante da compra.</p>
      </div>
    </header>

    <nav className="vf-sale-tabs" aria-label="Vendas de balcão">
      {canEdit&&<button type="button" className={section==="new"?"is-active":""}
        aria-current={section==="new"?"page":undefined}
        onClick={()=>openSection("new")}>
        <Plus size={17}/> Nova venda
      </button>}
      <button type="button" className={section==="history"?"is-active":""}
        aria-current={section==="history"?"page":undefined}
        onClick={()=>openSection("history")}>
        <ClipboardCheck size={17}/> Histórico
        {pending>0&&<span className="vf-sale-tab-count">{pending}</span>}
      </button>
    </nav>

    {error&&<div className="vf-sales-error" role="alert">{error}</div>}
    {message&&<div className="vf-sales-success" role="status">
      <CheckCircle2 size={19}/>
      <span>{message}</span>
      {section==="new"&&<button type="button" onClick={()=>openSection("history")}>
        Ver histórico <ArrowRight size={15}/>
      </button>}
    </div>}

    {section==="new"&&canEdit&&<section className="vf-sale-card" aria-labelledby="vf-new-sale-heading">
      <div className="vf-sale-card-heading">
        <div><span className="vf-sale-overline">NOVA VENDA</span>
          <h3 id="vf-new-sale-heading">Informações da compra</h3>
        </div>
        <span className="vf-sale-step">3 informações</span>
      </div>

      <form className="vf-sale-simple-form" onSubmit={save}>
        <div className="vf-sale-field">
          <label htmlFor="vf-sale-client"><span className="vf-sale-number">1</span> Quem comprou?</label>
          <select id="vf-sale-client" value={selected}
            onChange={e=>setSelected(e.target.value)}>
            <option value="__choose__" disabled>Selecione o cliente</option>
            <option value="">Cliente ainda não participa do clube</option>
            {people.map(item=><option key={item.id} value={item.id}>
              {item.display_name||"Participante"} · {item.contact_email}
            </option>)}
            {selected!==""&&selected!=="__choose__"&&!people.some(item=>item.id===selected)&&
              <option value={selected}>Cliente selecionado anteriormente</option>}
          </select>
          <div className="vf-sale-inline-help">
            <button type="button" aria-expanded={searchOpen}
              onClick={()=>setSearchOpen(v=>!v)}>
              <Search size={15}/> {searchOpen?"Fechar busca":"Não encontrou? Buscar cliente"}
            </button>
          </div>
          {searchOpen&&<label className="vf-sale-search-field" htmlFor="vf-sale-search">
            Nome ou e-mail do participante
            <input id="vf-sale-search" type="search" maxLength={80}
              placeholder="Digite para localizar o cliente"
              value={personQuery} onChange={e=>setPersonQuery(e.target.value)}/>
          </label>}
          {peopleError&&<p className="vf-sale-field-notice" role="status">
            Não foi possível carregar os participantes. Tente buscar novamente.
          </p>}
          {selected===""&&<p className="vf-sale-field-notice">
            Esta venda ficará registrada sem pontos. Convide o cliente a participar do clube.
          </p>}
        </div>

        <div className="vf-sale-field">
          <label htmlFor="vf-sale-amount"><span className="vf-sale-number">2</span> Qual foi o valor?</label>
          <div className="vf-sale-amount-input">
            <span aria-hidden="true">R$</span>
            <input id="vf-sale-amount" required inputMode="decimal"
              placeholder="89,90" value={amount} maxLength={12}
              onChange={e=>setAmount(e.target.value)}/>
          </div>
          <small>Informe o valor da compra elegível para o programa.</small>
        </div>

        <div className="vf-sale-field">
          <label htmlFor="vf-sale-receipt"><span className="vf-sale-number">3</span> Número do cupom ou recibo</label>
          <input id="vf-sale-receipt" required maxLength={80}
            value={receipt} placeholder="Ex.: 0042"
            autoComplete="off" onChange={e=>setReceipt(e.target.value)}/>
          <small>Use o número real do comprovante. Ele evita registrar a mesma venda duas vezes.</small>
        </div>

        <div className="vf-sale-advanced">
          <button type="button" aria-expanded={customTime}
            onClick={()=>{setCustomTime(v=>!v);setPaidAt(localNow());}}>
            <Clock3 size={15}/> A compra foi em outra data?
          </button>
          {customTime&&<label htmlFor="vf-sale-date">
            Data e hora da venda
            <input id="vf-sale-date" type="datetime-local" step={1}
              value={paidAt} onChange={e=>setPaidAt(e.target.value)} required/>
          </label>}
        </div>

        <div className="vf-sale-form-footer">
          <div className="vf-sale-guard"><ShieldCheck size={18}/>
            <span>Registro seguro. Os pontos só serão liberados quando o motor de fidelidade estiver ativo.</span>
          </div>
          <button className="vf-sale-submit" type="submit" disabled={busy}>
            {busy?"Registrando…":"Registrar venda"} <ArrowRight size={18}/>
          </button>
        </div>
      </form>
    </section>}

    {section==="history"&&<section className="vf-sale-card" aria-labelledby="vf-sale-history-heading">
      <div className="vf-sale-card-heading">
        <div><span className="vf-sale-overline">ACOMPANHAMENTO</span>
          <h3 id="vf-sale-history-heading">Vendas registradas</h3>
        </div>
        <button type="button" className="vf-sale-refresh" onClick={()=>setVersion(v=>v+1)}>
          <RefreshCw size={16}/> Atualizar
        </button>
      </div>
      {loading?<p role="status" className="vf-sale-loading">Carregando vendas…</p>:
        items.length===0?<div className="vf-sale-empty">
          <FileText size={28}/><strong>Nenhuma venda registrada por aqui.</strong>
          <p>As compras de balcão aparecerão aqui após o registro.</p>
          {canEdit&&<button type="button" onClick={()=>openSection("new")}>Registrar primeira venda</button>}
        </div>:
        <ul className="vf-sale-record-list">
          {items.map(item=><li className="vf-sale-record" key={item.id}>
            <div className="vf-sale-record-top">
              <div><strong>{item.reference}</strong>
                <span>{item.participant_name||"Cliente fora do clube"}</span>
                <small>{new Date(item.reported_paid_at).toLocaleString("pt-BR")}</small>
              </div>
              <div className="vf-sale-record-right">
                <strong>{money(item.eligible_amount_cents)}</strong>
                <span className={"vf-sale-state "+statusClass[item.state]}>
                  {statusText[item.state]}
                </span>
              </div>
            </div>
            <div className="vf-sale-record-actions">
              <span>Nenhum ponto creditado nesta etapa.</span>
              {item.state==="awaiting_review"&&!item.submitted_by_me&&canEdit?
                <button type="button" onClick={()=>{
                  setReviewing(item);setReviewNote("");
                }}>Conferir comprovante <ArrowRight size={15}/></button>:
                item.state==="awaiting_review"&&item.submitted_by_me?
                  <span>Outro administrador precisa conferir</span>:null}
            </div>
            {reviewing?.id===item.id&&<div className="vf-sale-review">
              <h4>Conferir o comprovante</h4>
              <p>Verifique o recibo <strong>{item.evidence_reference}</strong> e o valor
                de <strong>{money(item.eligible_amount_cents)}</strong> antes de concluir.</p>
              <label htmlFor="vf-sale-review-note">Como você conferiu?
                <textarea id="vf-sale-review-note" value={reviewNote}
                  onChange={e=>setReviewNote(e.target.value)}
                  placeholder="Ex.: Cupom e pagamento conferidos no caixa."
                  minLength={10} maxLength={240} rows={3} required/>
              </label>
              <div className="vf-sale-review-buttons">
                <button type="button" onClick={()=>setReviewing(null)}>Cancelar</button>
                <button type="button" disabled={busy||reviewNote.trim().length<10}
                  onClick={()=>void review("reject")}>Rejeitar</button>
                <button type="button" className="vf-sale-submit"
                  disabled={busy||reviewNote.trim().length<10}
                  onClick={()=>void review("approve")}>
                  Confirmar conferência <CheckCircle2 size={17}/>
                </button>
              </div>
              <p className="vf-sale-review-footnote">
                Conferir o recibo não libera pontos automaticamente.
              </p>
            </div>}
          </li>)}
        </ul>}
    </section>}

    {!canEdit&&section==="new"&&<section className="vf-sale-card">
      <UsersRound size={25}/><h3>Registro disponível para administradores</h3>
      <p>Esta conta pode acompanhar vendas, mas não criar registros.</p>
    </section>}
  </div>;
}
