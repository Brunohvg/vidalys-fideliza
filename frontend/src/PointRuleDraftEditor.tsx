import {useEffect,useState,type FormEvent} from "react";
import {Calculator, CheckCircle2, Settings2, ShieldCheck} from "lucide-react";
import {ApiError, merchantApi, type PointRuleDraft, type Store} from "./api";
import "./sales-workspace.css";

export default function PointRuleDraftEditor({tenantId,role,onRuleSaved}:{
  tenantId:string;role:Store["role"];onRuleSaved?:()=>void;
}){
  const [rule,setRule]=useState<Omit<PointRuleDraft,"version">>({
    points:1,per_cents:100,hold_days:7,validity_days:180,
  });
  const [baseMoney,setBaseMoney]=useState("1,00");
  const parsedBase=/^\d{1,7}(?:[,.]\d{1,2})?$/.test(baseMoney.trim())
    ? Number(baseMoney.trim().replace(",","."))*100 : NaN;
  const baseCents=Number.isSafeInteger(Math.round(parsedBase))&&parsedBase>=100
    &&parsedBase<=100_000_000?Math.round(parsedBase):null;
  const [version,setVersion]=useState<number|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const canEdit=role==="owner"||role==="admin";
  useEffect(()=>{
    let mounted=true;
    merchantApi.getPointRuleDraft(tenantId).then(result=>{
      if(mounted&&result.rule){
        setVersion(result.rule.version);
        setBaseMoney((result.rule.per_cents/100).toFixed(2).replace(".",","));
        setRule({
          points:result.rule.points,per_cents:result.rule.per_cents,
          hold_days:result.rule.hold_days,validity_days:result.rule.validity_days,
        });
      }
    }).catch(cause=>{
      if(mounted)setError(cause instanceof ApiError?cause.message:"Erro ao consultar a regra.");
    }).finally(()=>{if(mounted)setLoading(false)});
    return()=>{mounted=false};
  },[tenantId]);

  const save=async(e:FormEvent)=>{
    e.preventDefault();if(busy||!canEdit)return;
    if(baseCents===null){setError("Informe o valor base em reais, por exemplo 1,00.");return;}
    setBusy(true);setError("");setMessage("");
    try{
      const updated=await merchantApi.savePointRuleDraft(tenantId,{
        ...rule,per_cents:baseCents,
      });
      setVersion(updated.version);
      onRuleSaved?.();
      setMessage("Regra salva como rascunho. Nenhum ponto foi concedido.");
    }catch(cause){
      setError(cause instanceof ApiError?cause.message:"Falha ao salvar regra.");
    }finally{setBusy(false)}
  };
  const money=((baseCents??rule.per_cents)/100).toLocaleString("pt-BR",{
    style:"currency",currency:"BRL",
  });
  return <section className="vf-sales-card vf-rule-card">
    <div className="vf-sales-title"><Calculator size={23}/><div>
      <span className="portal-eyebrow">REGRAS DO CLUBE · RASCUNHO</span>
      <h3>Como o participante vai ganhar pontos?</h3>
      <p>Simule uma regra de acúmulo. A ativação só será disponibilizada após validar
        pagamentos, estornos e a carteira de pontos.</p>
    </div><span className="vf-rule-draft-label">Não publicado</span></div>
    {error&&<p className="vf-sales-error" role="alert">{error}</p>}
    {message&&<p className="vf-sales-success" role="status">{message}</p>}
    {loading?<p role="status">Carregando regras…</p>:
      <form className="vf-rule-form" onSubmit={save}>
        <label>Pontos gerados
          <input aria-label="Pontos por faixa" type="number" min={1} max={100000} step={1}
            disabled={!canEdit} value={rule.points}
            onChange={e=>setRule(v=>({...v,points:e.target.valueAsNumber}))}/>
        </label>
        <label>A cada valor elegível (R$)
          <input aria-label="Valor base em reais" inputMode="decimal" placeholder="1,00"
            disabled={!canEdit} value={baseMoney} maxLength={12}
            onChange={e=>setBaseMoney(e.target.value)}/>
        </label>
        <label>Carência (dias)
          <input aria-label="Carência em dias" type="number" min={0} max={90} step={1}
            disabled={!canEdit} value={rule.hold_days}
            onChange={e=>setRule(v=>({...v,hold_days:e.target.valueAsNumber}))}/>
        </label>
        <label>Validade após liberação (dias)
          <input aria-label="Validade em dias" type="number" min={1} max={1095} step={1}
            disabled={!canEdit} value={rule.validity_days}
            onChange={e=>setRule(v=>({...v,validity_days:e.target.valueAsNumber}))}/>
        </label>
        <div className="vf-rule-summary"><CheckCircle2 size={18}/>
          <span>Regra simulada: <strong>{rule.points} ponto(s) a cada {money}</strong> de compra elegível.
            Saldo ficará pendente por {rule.hold_days} dia(s), se a regra for publicada no futuro.</span>
        </div>
        <div className="vf-sales-form-bottom">
          <p><ShieldCheck size={14}/> {version===null?"Nenhuma regra salva.":"Versão de rascunho "+version+"."}
            {" "}Sem ativação financeira, resgates ou créditos automáticos.</p>
          {canEdit&&<button type="submit" className="portal-primary" disabled={busy||baseCents===null}>
            <Settings2 size={17}/>{busy?"Salvando…":"Salvar rascunho"}
          </button>}
        </div>
      </form>}
  </section>;
}
