import {useEffect,useRef,useState,type FormEvent} from "react";
import {
  ArrowRight,BookOpen,Check,CheckCircle2,Globe2,HeartHandshake,
  LockKeyhole,Mail,Palette,RefreshCw,Save,Settings2,ShieldCheck,TriangleAlert,ShoppingBag,FileText,Download
} from "lucide-react";
import {
  ApiError,merchantApi,type NuvemshopConnectionStatus,
  type Store,type TenantBranding,type TenantPreferences,type PrivacyRequestsSummary,
} from "./api";
import {readableForeground} from "./brand-contrast";
import "./store-settings.css";

type Props={
  tenantId:string;role:Store["role"];
  onGoToProgram:()=>void;
};
function Status({ready,label}:{ready:boolean;label:string}){
  return <span className={"ss-state "+(ready?"is-ready":"is-pending")}>
    {ready?<CheckCircle2 size={14}/>:<LockKeyhole size={14}/>}
    {label}
  </span>;
}
function friendlyError(error:unknown,defaultMessage:string){
  // Esconder detalhes técnicos de falhas de integração do painel do lojista.
  if(error instanceof ApiError){
    if(error.status===409)return "Essas informações mudaram. Atualize a página antes de tentar novamente.";
    if(error.status===403)return "Seu usuário não tem autorização para realizar esta ação.";
    if(error.status===429)return "Já houve uma tentativa recente. Tente novamente em alguns instantes.";
    if(error.status===503)return "Conexão temporariamente indisponível. Tente novamente mais tarde.";
  }
  return defaultMessage;
}

export default function StoreSettings({tenantId,role,onGoToProgram}:Props){
  const [settings,setSettings]=useState<TenantPreferences|null>(null);
  const [integration,setIntegration]=useState<NuvemshopConnectionStatus|null>(null);
  const [privacy,setPrivacy]=useState<PrivacyRequestsSummary|null>(null);
  const [reportBusy,setReportBusy]=useState<string|null>(null);
  const [reportDownloads,setReportDownloads]=useState<Record<string,{digest:string;complete:boolean}>>({});
  const [brand,setBrand]=useState<TenantBranding|null>(null);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [connecting,setConnecting]=useState(false);
  // Resultado temporario: nunca confundir teste pontual com prova persistida.
  const [liveCheck,setLiveCheck]=useState<"idle"|"running"|"verified"|"failed">("idle");
  const checkSequence=useRef(0);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const editable=role==="owner"||role==="admin";
  const dirty=Boolean(settings&&brand&&JSON.stringify(brand)!==JSON.stringify(settings.branding));

  useEffect(()=>{
    let current=true;
    checkSequence.current++;
    setLiveCheck("idle");
    setLoading(true);setSettings(null);setIntegration(null);setPrivacy(null);
    setReportDownloads({});
    setBrand(null);setError("");setNotice("");
    Promise.all([
      merchantApi.getTenantSettings(tenantId),
      merchantApi.nuvemshopStatus(tenantId).catch(()=>null),
      editable?merchantApi.getTenantPrivacyRequests(tenantId).catch(()=>null):Promise.resolve(null)
    ]).then(([prefs,link,requests])=>{
      if(!current)return;
      setSettings(prefs);setBrand(prefs.branding);setIntegration(link);
      setPrivacy(requests);
      // O callback da loja retorna aqui, não à consulta do catálogo.
      // Nunca confiar apenas no parâmetro da URL para afirmar conexão.
      const query=new URLSearchParams(window.location.search);
      const result=query.get("nuvemshop");
      if(result==="connected"||result==="failed"){
        const sourceTenant=query.get("nuvemshop_tenant");
        query.delete("nuvemshop");query.delete("nuvemshop_tenant");
        const remaining=query.toString();
        window.history.replaceState(null,"",window.location.pathname+
          (remaining?"?"+remaining:"")+window.location.hash);
        if(sourceTenant && sourceTenant!==tenantId){
          setError("A autorização retornou para outra loja. Confira a loja selecionada.");
        }else if(result==="failed"){
          setError("A autorização não foi concluída. Tente novamente em Configurações.");
        }else if(link?.connected){
          setNotice("Autorização registrada. Verifique o acesso à Nuvemshop antes de usar o catálogo.");
        }else{
          setError("A autorização retornou, mas a conexão não foi confirmada. Atualize a página.");
        }
      }
    }).catch(()=>{
      if(current)setError("Não foi possível carregar as configurações da loja.");
    }).finally(()=>{if(current)setLoading(false)});
    return ()=>{current=false};
  },[tenantId]);

  const update=(key:keyof TenantBranding,value:string)=>
    setBrand(old=>old?{...old,[key]:value}:old);
  const save=async(event:FormEvent)=>{
    event.preventDefault();
    if(!settings||!brand||!editable||!dirty||saving)return;
    setSaving(true);setError("");setNotice("");
    try{
      const result=await merchantApi.saveTenantBranding(tenantId,settings.version,brand);
      setSettings({...settings,branding:result.branding,version:result.version});
      setBrand(result.branding);
      setNotice(result.updated
        ?"Alterações salvas. Suas cores e seu nome serão usados na página do programa quando ela estiver disponível."
        :"Suas preferências já estão atualizadas.");
    }catch(cause){
      setError(friendlyError(cause,"Não foi possível salvar. Confira os campos e tente novamente."));
    }finally{setSaving(false);}
  };
  const reconnect=async()=>{
    if(!editable||connecting)return;
    setConnecting(true);setError("");setNotice("");
    try{
      const result=await merchantApi.beginNuvemshopOAuth(tenantId);
      const url=new URL(result.authorize_url);
      if(url.protocol!=="https:"||url.hostname!=="www.tiendanube.com"||
          !/^\/apps\/[0-9]+\/authorize$/.test(url.pathname)){
        throw new Error("Endereço de autorização não reconhecido.");
      }
      window.location.assign(url.toString());
    }catch(cause){
      setError(friendlyError(cause,"Não foi possível atualizar a conexão com sua loja."));
      setConnecting(false);
    }
  };

  const verifyReadAccess=async()=>{
    if(!editable||!integration?.connected||settings?.tenant_status!=="active"||
       integration.connection_check?.catalog_scope_granted===false||
       liveCheck==="running")return;
    const sequence=++checkSequence.current;
    setLiveCheck("running");setError("");setNotice("");
    try{
      // Reutiliza a consulta GET oficial, ja protegida por RBAC,
      // tenant, rate-limit e token server-side. Sem endpoint duplicado.
      const preview=await merchantApi.previewLiveNuvemshop(tenantId,1);
      if(preview.source!=="nuvemshop_live_read_only"||
         preview.writes_performed!==0)throw new Error("Resposta inesperada");
      if(sequence!==checkSequence.current)return;
      setLiveCheck("verified");
      setNotice("Acesso de leitura confirmado nesta sessão. A Nuvemshop respondeu à consulta sem alterar produtos.");
    }catch(cause){
      if(sequence!==checkSequence.current)return;
      setLiveCheck("failed");
      setError(friendlyError(cause,
        "Não foi possível verificar o acesso. Confira a autorização da loja e tente novamente."));
    }
  };

  const downloadReport=async(requestId:string)=>{
    if(reportBusy)return;
    setReportBusy(requestId);setError("");setNotice("");
    try{
      const file=await merchantApi.downloadPrivacyReport(tenantId,requestId);
      if(!/^[0-9a-f]{64}$/.test(file.digest)){
        throw new Error("Relatório sem comprovante válido.");
      }
      const local=URL.createObjectURL(file.blob);
      const link=document.createElement("a");
      link.href=local;
      link.download="relatorio-fideliza-"+requestId+".json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(()=>URL.revokeObjectURL(local),1000);
      setReportDownloads(old=>({...old,[requestId]:{
        digest:file.digest,complete:file.complete,
      }}));
      setNotice(file.complete
        ?"O arquivo foi preparado. Confira o conteúdo antes de confirmar o recebimento."
        :"O relatório parcial foi preparado. A Vidalys precisa revisar os dados antes de encerrar o pedido.");
    }catch(cause){
      setError(friendlyError(cause,"Não foi possível preparar o relatório. Tente novamente."));
    }finally{setReportBusy(null);}
  };
  const confirmReport=async(requestId:string)=>{
    const item=reportDownloads[requestId];
    if(!item?.complete||reportBusy)return;
    setReportBusy(requestId);setError("");setNotice("");
    try{
      const result=await merchantApi.confirmPrivacyReport(tenantId,requestId,item.digest);
      setPrivacy(old=>old?{...old,
        pending_total:Math.max(0,old.pending_total-1),
        access_requests:Math.max(0,old.access_requests-1),
        items:old.items.filter(entry=>entry.id!==requestId),
      }:old);
      setReportDownloads(old=>{
        const next={...old};
        delete next[requestId];
        return next;
      });
      setNotice(result.message);
    }catch(cause){
      setError(friendlyError(cause,"Não foi possível confirmar. Baixe novamente o relatório se os dados mudaram."));
    }finally{setReportBusy(null);}
  };

  if(loading)return <section className="ss-loading" role="status">
    <RefreshCw size={20} className="portal-spin"/> Carregando suas preferências…
  </section>;
  if(!settings||!brand)return <section className="ss-feedback ss-error" role="alert">
    {error||"As configurações não estão disponíveis no momento."}
  </section>;
  const connected=Boolean(integration?.connected);
  const customerReady=Boolean(integration?.customer_matching?.read_only_preview_available);
  const connectionStep=integration?.connection_check?.next_step;
  const connectionExplanation=liveCheck==="verified"
    ?"Consulta real concluída nesta sessão. O acesso de leitura foi confirmado, sem alterar a loja."
    :connectionStep==="activate_tenant"
    ?"Sua loja precisa estar ativa para utilizar a integração."
    :connectionStep==="configure_app"
      ?"O aplicativo ainda precisa ser configurado pela equipe Vidalys na plataforma."
      :connectionStep==="authorize_store"
        ?"Autorize a conexão da sua loja pela Nuvemshop para começar."
        :connectionStep==="grant_read_products_and_reinstall"
          ?"Falta autorização para consultar produtos. Ajuste a permissão no Portal de Parceiros e reinstale o aplicativo nesta loja."
          :connectionStep==="verify_catalog_with_live_get"
            ?"A autorização está registrada. Faça uma consulta real de produtos em Conciliação para verificar se o acesso continua válido."
            :!integration?.configured
              ?"A conexão ainda está sendo preparada pela plataforma."
              :"A instalação ainda não foi verificada.";
  const enrollmentReady=Boolean(settings.features.public_signup_enabled&&
    settings.tenant_status==="active");
  const programName=brand.program_name||("Clube "+settings.tenant_name);
  const programColor=/^#[0-9A-Fa-f]{6}$/.test(brand.primary_color)?brand.primary_color:"#087F79";
  const accent=/^#[0-9A-Fa-f]{6}$/.test(brand.accent_color)?brand.accent_color:"#37D5BB";

  return <div className="ss-root">
    <div className="ss-intro">
      <div className="ss-intro-icon"><Settings2 size={23}/></div>
      <div><span className="portal-eyebrow">SUA LOJA, SUA IDENTIDADE</span>
        <h2>Configurações</h2>
        <p>Escolha como seus clientes vão conhecer seu programa e acompanhe o que já está disponível.</p>
      </div>
    </div>
    {error&&<div className="ss-feedback ss-error" role="alert"><TriangleAlert size={17}/>{error}</div>}
    {notice&&<div className="ss-feedback ss-success" role="status"><Check size={17}/>{notice}</div>}
    <div className="ss-layout">
      <section className="ss-card" aria-labelledby="ss-brand-title">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><Palette size={21}/></div>
          <div><h3 id="ss-brand-title">Aparência do programa</h3>
            <p>Personalize o nome e as cores que seus clientes vão ver.</p></div>
        </div>
        <div className="ss-brand-layout">
          <form className="ss-form" onSubmit={save}>
            <label>Nome do clube de vantagens
              <input value={brand.program_name}
                onChange={e=>update("program_name",e.target.value)} maxLength={80}
                disabled={!editable||saving} placeholder={"Clube "+settings.tenant_name}/>
              <small>Exemplo: Clube Bibelô. Se deixar vazio, usamos o nome da sua loja.</small>
            </label>
            <div className="ss-color-grid">
              <label>Cor principal
                <div className="ss-color-control">
                  <input type="color" value={programColor}
                    disabled={!editable||saving}
                    onChange={e=>update("primary_color",e.target.value)}/>
                  <span>{brand.primary_color}</span>
                </div>
                <small>Cor dos botões e destaques principais.</small>
              </label>
              <label>Cor de destaque
                <div className="ss-color-control">
                  <input type="color" value={accent}
                    disabled={!editable||saving}
                    onChange={e=>update("accent_color",e.target.value)}/>
                  <span>{brand.accent_color}</span>
                </div>
                <small>Usada em pequenos detalhes do programa.</small>
              </label>
            </div>
            <label>E-mail para dúvidas dos participantes
              <input value={brand.support_email}
                onChange={e=>update("support_email",e.target.value)}
                disabled={!editable||saving} maxLength={254}
                type="email" autoComplete="off" placeholder="atendimento@sualoja.com.br"/>
              <small>O contato que o cliente poderá usar para falar com sua loja.</small>
            </label>
            {editable&&<div className="ss-action-row">
              <button className="portal-primary" disabled={!dirty||saving} type="submit">
                <Save size={16}/>{saving?"Salvando…":"Salvar alterações"}
              </button>
            </div>}
            {!editable&&<p className="ss-readonly">Você pode consultar estas opções. Um administrador da loja pode alterá-las.</p>}
          </form>
          <aside className="ss-live-card" aria-label="Prévia da página do clube">
            <div className="ss-preview-stage" style={{
              background:programColor,
              color:readableForeground(programColor),
            }}>
              <div className="ss-preview-icon" style={{
                background:accent,
                color:readableForeground(accent),
              }}><HeartHandshake size={21}/></div>
              <span>COMO SEU CLIENTE VAI VER</span>
              <strong>{programName}</strong>
              <p>Uma relação que vale mais. Conheça as vantagens do seu clube.</p>
              <div className="ss-preview-button">Conhecer meu clube <ArrowRight size={16}/></div>
            </div>
            <div className="ss-preview-caption"><ShieldCheck size={15}/>
              Esta é uma prévia visual. Ela não publica seu programa.
            </div>
          </aside>
        </div>
      </section>
      <section className="ss-card" aria-labelledby="ss-store-connection">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><ShoppingBag size={20}/></div>
          <div><h3 id="ss-store-connection">Conexão com a loja</h3>
            <p>Conecte sua loja para aproveitar os recursos do Fideliza.</p></div>
        </div>
        <div className="ss-integration">
          <div className="ss-service-label"><span className="ss-service-icon"><ShoppingBag size={20}/></span>
            <div><strong>Nuvemshop</strong><small>Sua loja virtual</small></div>
          </div>
          <Status ready={connected} label={connected?"Autorização registrada":"Não vinculada"}/>
        </div>
        <p className="ss-muted">{connectionExplanation}</p>
        {connected&&<p className="ss-muted">{customerReady
          ?"Consulta de cadastros consentidos disponível para teste, sem ativar benefícios."
          :"A leitura de clientes permanece condicionada às permissões e à homologação."}</p>}
        {editable&&<button type="button" className="ss-secondary" onClick={()=>void reconnect()}
          disabled={connecting||!integration?.configured}>
          <RefreshCw size={16}/>{connecting?"Abrindo sua loja…":connected?"Atualizar conexão":"Conectar minha loja"}
          <ArrowRight size={15}/>
        </button>}
        {editable&&!integration?.configured&&<p className="ss-muted">
          A conexão estará disponível assim que a plataforma concluir a preparação da sua loja.</p>}
        {editable&&connected&&integration?.connection_check?.catalog_scope_granted!==false&&
          settings.tenant_status==="active"&&<>
            <button type="button" className="ss-secondary"
              disabled={liveCheck==="running"} onClick={()=>void verifyReadAccess()}>
              <ShieldCheck size={16}/>{liveCheck==="running"
                ?"Conferindo acesso…":liveCheck==="verified"
                  ?"Conferir acesso novamente":"Verificar acesso à Nuvemshop"}
            </button>
            <p className="ss-muted" role="status" aria-live="polite">
              {liveCheck==="verified"
                ?"Acesso verificado agora. Esta confirmação vale apenas para esta sessão."
                :liveCheck==="failed"
                  ?"Acesso não verificado. A autorização pode precisar ser atualizada."
                  :liveCheck==="running"
                    ?"Consultando a Nuvemshop sem modificar seus produtos…"
                    :"A autorização salva ainda não comprova acesso atual. Faça uma consulta de leitura."}
            </p>
          </>}

        <div className="ss-divider"/>
        <div className="ss-integration">
          <div className="ss-service-label"><span className="ss-service-icon"><Mail size={20}/></span>
            <div><strong>Confirmação por e-mail</strong>
              <small>Para que os participantes confirmem o cadastro com segurança</small>
            </div>
          </div>
          <Status ready={settings.features.email_delivery_enabled}
            label={settings.features.email_delivery_enabled?"Configurada":"Em preparação"}/>
        </div>
        <p className="ss-muted">As mensagens de confirmação serão usadas quando o cadastro de participantes estiver disponível.</p>
      </section>
      <section className="ss-card" aria-labelledby="ss-program-title">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><BookOpen size={20}/></div>
          <div><h3 id="ss-program-title">Regras do clube</h3>
            <p>Defina as condições antes de convidar seus clientes.</p></div>
        </div>
        <div className="ss-config-row"><div>
            <strong>Cadastro de participantes</strong>
            <p>Seus clientes poderão solicitar adesão depois que as regras estiverem prontas.</p>
          </div>
          <Status ready={enrollmentReady} label={enrollmentReady?"Disponível":"Em preparação"}/>
        </div>
        <div className="ss-config-row"><div>
            <strong>Recompensas</strong>
            <p>Os benefícios serão liberados quando o programa estiver pronto para funcionar.</p>
          </div>
          <Status ready={false} label="Em breve"/>
        </div>
        <button type="button" className="ss-secondary" onClick={onGoToProgram}>
          <BookOpen size={16}/> Gerenciar no Programa <ArrowRight size={15}/>
        </button>
      </section>
      <section className="ss-card" aria-labelledby="ss-domains-title">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><Globe2 size={20}/></div>
          <div><h3 id="ss-domains-title">Página do clube</h3>
            <p>Um espaço exclusivo para seus clientes conhecerem o programa.</p></div>
        </div>
        <div className="ss-domain">
          <div><small>Seu endereço do programa</small>
            <strong>{enrollmentReady
              ?"A página ficará disponível após a aprovação das regras."
              :"Estamos preparando a página do seu clube."}</strong></div>
          <div><small>Usar o endereço da sua própria loja</small>
            <strong>Em breve você poderá escolher um endereço personalizado.</strong></div>
        </div>
        <p className="ss-muted">Você não precisa alterar o site da sua loja para personalizar o clube.</p>
      </section>
      {editable&&<section className="ss-card" aria-labelledby="ss-privacy-title">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><FileText size={20}/></div>
          <div><h3 id="ss-privacy-title">Privacidade dos participantes</h3>
            <p>Acompanhe os pedidos de acesso ou exclusão dos dados do programa.</p></div>
        </div>
        {privacy
          ? <div className="ss-privacy-summary">
              <div><strong>{privacy.pending_total}</strong><span>Solicitações em análise</span></div>
              <div><strong>{privacy.access_requests}</strong><span>Pedidos de dados</span></div>
              <div><strong>{privacy.deletion_requests}</strong><span>Pedidos de exclusão</span></div>
            </div>
          : <p className="ss-muted">Não foi possível consultar as solicitações agora.</p>}
        {privacy?.items.length===0&&<p className="ss-muted">
          Não há solicitações pendentes registradas para esta loja.</p>}
        {privacy?.items.length? <ul className="ss-privacy-list">
          {privacy.items.map(item=><li key={item.id}>
            <div className="ss-privacy-entry">
              <span>{item.type==="data_access"?"Pedido de acesso aos dados":"Pedido de exclusão de dados"}</span>
              <small>{new Date(item.received_at).toLocaleDateString("pt-BR")}
                {" · "}Em análise</small>
              {item.type==="deletion"&&<small>{item.protection_applied
                ?"Dados de contato protegidos. Revisão final em andamento."
                :"Solicitação recebida. Proteção dos dados em andamento."}</small>}
            </div>
            {item.report_available&&<div className="ss-privacy-actions">
              <button type="button" className="ss-secondary"
                disabled={reportBusy!==null}
                onClick={()=>void downloadReport(item.id)}>
                <Download size={15}/>{reportBusy===item.id?"Preparando…":"Baixar relatório"}
              </button>
              {reportDownloads[item.id]?.complete&&<button type="button"
                className="ss-secondary ss-report-confirm"
                disabled={reportBusy!==null}
                onClick={()=>void confirmReport(item.id)}>
                <Check size={15}/>Confirmar que recebi
              </button>}
              {reportDownloads[item.id]&&!reportDownloads[item.id].complete&&
                <small>O relatório precisa de revisão para concluir o pedido.</small>}
            </div>}
          </li>)}
        </ul>:null}
        <p className="ss-muted">
          O cliente faz o pedido à loja. A Vidalys protege os dados mantidos no
          Fideliza e acompanha a eliminação. A loja responde ao cliente.
          Registros sujeitos à retenção legal exigem análise antes da conclusão.
        </p>
      </section>}
    </div>
    <div className="ss-security-note"><ShieldCheck size={18}/>
      Alterar seu clube aqui não muda preços, estoque nem pedidos da sua loja.
    </div>
  </div>;
}
