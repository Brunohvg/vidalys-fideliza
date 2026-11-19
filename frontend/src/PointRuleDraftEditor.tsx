import {useEffect,useState,type FormEvent} from "react";
import {Calculator, CheckCircle2, Settings2, ShieldCheck} from "lucide-react";
import {ApiError, merchantApi, type PointRuleDraft, type Store} from "./api";
import "./sales-workspace.css";

/* Carência = dias entre a compra paga e a liberação dos pontos. Cada lojista
   escolhe a sua; as opções prontas só facilitam a decisão. */
const HOLD_PRESETS=[
  {days:0,label:"Na hora",hint:"Bom para balcão, onde a troca é rara."},
  {days:7,label:"7 dias",hint:"Cobre o direito de arrependimento das compras online."},
  {days:30,label:"30 dias",hint:"Cobre o prazo de troca da maioria das lojas."},
] as const;
function holdExplanation(days:number){
  if(!Number.isInteger(days)||days<0||days>90)return "Use um número de 0 a 90 dias.";
  if(days===0)return "Os pontos aparecem como disponíveis logo após a compra paga. Se houver devolução, o saldo pode ficar negativo até ser ajustado.";
  return `Os pontos ficam pendentes por ${days} dia${days===1?"":"s"} depois da compra paga. Se a compra for cancelada ou devolvida nesse prazo, os pontos são retirados antes de o cliente usar.`;
}

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
        <fieldset className="vf-hold">
          <legend>Quando os pontos ficam disponíveis?</legend>
          <div className="vf-hold-options" role="radiogroup" aria-label="Carência dos pontos">
            {HOLD_PRESETS.map(option=><button key={option.days} type="button" role="radio"
              aria-checked={rule.hold_days===option.days} disabled={!canEdit}
              className={rule.hold_days===option.days?"is-selected":""}
              onClick={()=>setRule(v=>({...v,hold_days:option.days}))}>
              <b>{option.label}</b><small>{option.hint}</small>
            </button>)}
          </div>
          <label className="vf-hold-custom">Outro prazo (dias)
            <input aria-label="Carência em dias" type="number" min={0} max={90} step={1}
              disabled={!canEdit} value={Number.isNaN(rule.hold_days)?"":rule.hold_days}
              onChange={e=>setRule(v=>({...v,hold_days:e.target.valueAsNumber}))}/>
          </label>
          <p className="vf-hold-explain" aria-live="polite">{holdExplanation(rule.hold_days)}</p>
        </fieldset>
        <label>Validade após liberação (dias)
          <input aria-label="Validade em dias" type="number" min={1} max={1095} step={1}
            disabled={!canEdit} value={rule.validity_days}
            onChange={e=>setRule(v=>({...v,validity_days:e.target.valueAsNumber}))}/>
        </label>
        <div className="vf-rule-summary"><CheckCircle2 size={18}/>
          <span>Regra simulada: <strong>{rule.points} ponto(s) a cada {money}</strong> de compra elegível.
            {rule.hold_days===0?" Pontos liberados na hora,":` Pontos liberados ${rule.hold_days} dia(s) após a compra paga,`} se a regra for publicada no futuro.</span>
        </div>
        <div className="vf-sales-form-bottom">
          <p><ShieldCheck size={14}/> {version===null?"Nenhuma regra salva.":"Versão de rascunho "+version+"."}
            {" "}Sem ativação financeira, resgates ou créditos automáticos.</p>
          {canEdit&&<button type="submit" className="portal-primary"
            disabled={busy||baseCents===null||!Number.isInteger(rule.hold_days)||rule.hold_days<0||rule.hold_days>90}>
            <Settings2 size={17}/>{busy?"Salvando…":"Salvar rascunho"}
          </button>}
        </div>
      </form>}
  </section>;
}
