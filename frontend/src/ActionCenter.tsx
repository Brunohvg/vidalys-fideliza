import {useEffect, useState} from "react";
import {
  ArrowRight, BarChart3, CheckCircle2, CircleHelp, Gift, HeartHandshake,
  LockKeyhole, PlugZap, ShieldCheck, Sparkles, UsersRound
} from "lucide-react";
import {merchantApi, type CampaignDraftList, type ParticipantDirectoryResponse, type NuvemshopConnectionStatus} from "./api";

type Destination = "clients"|"campaign"|"catalog"|"results"|"settings";
type Action = {
  title:string;
  body:string;
  reason:string;
  target:Destination;
  callToAction:string;
  icon:typeof Gift;
};

export default function ActionCenter({
  tenantId, onNavigate
}: {tenantId:string; onNavigate:(target:Destination)=>void}) {
  const [participants,setParticipants]=useState<ParticipantDirectoryResponse|null>(null);
  const [integration,setIntegration]=useState<NuvemshopConnectionStatus|null>(null);
  const [drafts,setDrafts]=useState<CampaignDraftList|null>(null);
  const [draftsError,setDraftsError]=useState(false);
  const [participantsError,setParticipantsError]=useState(false);
  const [integrationError,setIntegrationError]=useState(false);

  useEffect(()=>{
    let active=true;
    setParticipants(null);setIntegration(null);setDrafts(null);
    setParticipantsError(false);setIntegrationError(false);setDraftsError(false);
    merchantApi.listParticipants(tenantId).then(r=>{if(active)setParticipants(r)})
      .catch(()=>{if(active)setParticipantsError(true)});
    merchantApi.listCampaignDrafts(tenantId).then(r=>{if(active)setDrafts(r)})
      .catch(()=>{if(active)setDraftsError(true)});
    merchantApi.nuvemshopStatus(tenantId).then(r=>{if(active)setIntegration(r)})
      .catch(()=>{if(active)setIntegrationError(true)});
    return ()=>{active=false};
  },[tenantId]);

  const actions:Action[] = [];
  if (integration && !integration.connected) {
    actions.push({
      title:"Conecte sua Nuvemshop",
      body:integration.configured
        ?"Autorize a Nuvemshop para analisar uma amostra de produtos e variantes, sem alterar seu catálogo."
        :"A conexão será liberada depois da configuração segura do aplicativo na homologação.",
      reason:"O Fideliza ainda não recebe dados dessa loja.",
      target:"settings",callToAction:"Iniciar conexão",icon:PlugZap,
    });
  } else if (integration?.connected) {
    actions.push({
      title:"Confira o acesso à Nuvemshop",
      body:integration.connection_check?.catalog_scope_granted===false
        ?"A autorização existe, mas falta permissão de leitura dos produtos. Corrija no Portal de Parceiros e reinstale o aplicativo."
        :"A autorização foi registrada. Verifique a leitura real da loja antes de confiar na conexão.",
      reason:"Autorização registrada não prova que o token continua válido.",
      target:"settings",callToAction:"Verificar conexão",icon:PlugZap,
    });
  }
  if (participants && participants.summary.total===0) {
    actions.push({
      title:"Prepare a primeira adesão",
      body:"Defina as regras e o aceite do programa. Compradores da loja só poderão virar participantes após consentimento.",
      reason:"Não existem participantes cadastrados nesta loja.",
      target:"clients",callToAction:"Ver participantes",icon:HeartHandshake,
    });
  }
  if (participants && participants.summary.total>0) {
    actions.push({
      title:"Organize os participantes",
      body:"Confira as adesões registradas e as situações ativas ou pausadas. Nenhum benefício é enviado automaticamente.",
      reason:participants.summary.total+" participante(s) registrado(s) com aceite nesta loja.",
      target:"clients",callToAction:"Abrir clientes",icon:UsersRound,
    });
  }
  if(drafts?.items.length){
    const latest=drafts.items[0];
    actions.push({
      title:"Retome seu planejamento",
      body:"Você já começou “"+latest.title+"”. Continue de onde parou, confira o orçamento e revise os limites.",
      reason:drafts.items.length+" rascunho(s) salvo(s). Nenhuma campanha foi publicada.",
      target:"campaign",callToAction:"Retomar campanha",icon:Gift,
    });
  }else{
    actions.push({
      title:"Desenhe sua primeira campanha",
      body:"Escolha entre segunda compra, reativação ou recorrência. Faça uma prévia de orçamento em poucos passos.",
      reason:"O motor de benefícios ainda está em desenvolvimento; a ferramenta não publica campanhas.",
      target:"campaign",callToAction:"Planejar benefício",icon:Gift,
    });
  }
  if (actions.length<3) {
    actions.push({
      title:"Prepare a medição de resultados",
      body:"A futura área de resultados distinguirá compras, benefícios concedidos, resgates e recompras comprovadas.",
      reason:"Sem eventos e pedidos autorizados, ainda não há receita atribuível ao programa.",
      target:"results",callToAction:"Ver resultados",icon:BarChart3,
    });
  }

  const readiness = [
    {
      title:"Autorizar e verificar a loja",
      detail:"OAuth registrado não substitui o teste de acesso real.",
      status:integrationError?"unknown":integration?.connected?"authorized":"not_ready",
      destination:"settings" as const,action:"Configurar",
    },
    {
      title:"Receber participantes",
      detail:"Clientes precisam autorizar a entrada no clube.",
      status:participantsError?"unknown":participants?.summary.total
        ?"ready":"not_ready",
      destination:"clients" as const,action:"Ver clientes",
    },
    {
      title:"Planejar benefícios",
      detail:"Simule rentabilidade e salve uma campanha.",
      status:draftsError?"unknown":drafts?.items.length?"ready":"not_ready",
      destination:"campaign" as const,action:"Planejar",
    },
    {
      title:"Cashback nas compras",
      detail:"A concessão real exige pagamento confirmado e motor aprovado.",
      status:"locked",
      destination:null,action:"",
    },
  ];

  return <div className="xp-action-center">
    <section className="xp-action-banner">
      <div><span className="xp-eyebrow"><Sparkles size={16}/> FIDELIZAÇÃO INTELIGENTE</span>
        <h2>O que fazer agora para<br/><em>seus clientes voltarem?</em></h2>
        <p>Menos telas para configurar. Mais clareza sobre a próxima ação e o que precisa estar pronto antes de oferecer um benefício.</p>
        <div className="xp-action-safe"><ShieldCheck size={16}/> Sugestões explicáveis. Nenhuma ação é executada sem sua aprovação.</div>
      </div>
      <div className="xp-action-decoration" aria-hidden="true"><HeartHandshake size={75} strokeWidth={1.25}/></div>
    </section>

    <section className="xp-action-section">
      <div className="xp-section-heading"><span className="portal-eyebrow">PRÓXIMOS PASSOS DA LOJA</span>
        <h2>Seu plano de ação</h2>
        <p>Recomendações baseadas no estado conhecido do sistema, não em vendas inventadas.</p></div>
      {(integrationError||participantsError||draftsError) && <div className="xp-action-warning" role="status">
        <CircleHelp size={18}/> Alguns dados não puderam ser consultados. As sugestões abaixo não representam uma avaliação completa da loja.
      </div>}
      <div className="xp-action-cards">
        {actions.slice(0,3).map((action,i)=>{const Icon=action.icon;return <article key={action.title} className="xp-action-card">
          <div className="xp-action-top"><span className="xp-action-number">0{i+1}</span><span className="xp-action-icon"><Icon size={24}/></span></div>
          <h3>{action.title}</h3><p>{action.body}</p>
          <div className="xp-action-reason"><CircleHelp size={15}/>{action.reason}</div>
          <button type="button" onClick={()=>onNavigate(action.target)} className="xp-action-link">
            {action.callToAction} <ArrowRight size={17}/></button>
        </article>})}
      </div>
    </section>

    <section className="xp-journey" aria-labelledby="xp-journey-title">
      <div className="xp-section-heading">
        <span className="portal-eyebrow">EVOLUÇÃO DO SEU CLUBE</span>
        <h2 id="xp-journey-title">Sua jornada, sem atalhos.</h2>
        <p>Acompanhe os passos já disponíveis e saiba o que falta antes de oferecer cashback.</p>
      </div>
      <ol className="xp-journey-list">
        {readiness.map((step,index)=><li key={step.title}
          className={"xp-journey-item "+step.status}>
          <span className="xp-journey-number" aria-hidden="true">
            {step.status==="ready"?<CheckCircle2 size={20}/>:
             step.status==="locked"?<LockKeyhole size={18}/>:String(index+1).padStart(2,"0")}
          </span>
          <div className="xp-journey-copy">
            <strong>{step.title}</strong>
            <p>{step.detail}</p>
          </div>
          <span className="xp-journey-state">
            {step.status==="ready"?"Disponível":
             step.status==="locked"?"Ainda não liberado":
             step.status==="authorized"?"Autorizada; verificar":
             step.status==="unknown"?"Não foi possível verificar":"A preparar"}
          </span>
          {step.destination&&<button type="button" className="xp-journey-link"
            onClick={()=>onNavigate(step.destination)}>
            {step.action}<ArrowRight size={15}/>
          </button>}
        </li>)}
      </ol>
      <p className="xp-journey-safety">
        <ShieldCheck size={16}/> Um benefício só será aplicado quando
        o pedido pago e a regra financeira estiverem verificados.
      </p>
    </section>

    <section className="xp-ai-note">
      <span className="xp-ai-note-symbol"><Sparkles size={22}/></span>
      <div><strong>Próxima evolução: sugestões com IA</strong>
        <p>O Gemini poderá ajudar a escrever campanhas e explicar oportunidades com indicadores agregados. Antes de ativá-lo, vamos configurar o controle de privacidade e de custo da API. Nenhum dado de clientes é enviado a modelos externos nesta versão.</p>
      </div>
      <span className="xp-ai-stage"><LockKeyhole size={15}/> Ainda não conectado</span>
    </section>
  </div>;
}
