import {useEffect,useState,type FormEvent} from "react";
import {
  ArrowRight,BookOpen,Check,CheckCircle2,Cloud,Globe2,HeartHandshake,
  LockKeyhole,Mail,Palette,RefreshCw,Save,Settings2,ShieldCheck,TriangleAlert
} from "lucide-react";
import {
  ApiError,merchantApi,type NuvemshopConnectionStatus,
  type Store,type TenantBranding,type TenantPreferences,
} from "./api";
import "./store-settings.css";

type Props={
  tenantId:string;role:Store["role"];
  onGoToClients:()=>void;
};
function Status({ready,label}:{ready:boolean;label:string}){
  return <span className={"ss-state "+(ready?"is-ready":"is-pending")}>
    {ready?<CheckCircle2 size={14}/>:<LockKeyhole size={14}/>}
    {label}
  </span>;
}
function fallbackError(error:unknown,defaultMessage:string){
  return error instanceof ApiError?error.message:defaultMessage;
}
export default function StoreSettings({tenantId,role,onGoToClients}:Props){
  const [settings,setSettings]=useState<TenantPreferences|null>(null);
  const [integration,setIntegration]=useState<NuvemshopConnectionStatus|null>(null);
  const [brand,setBrand]=useState<TenantBranding|null>(null);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [connecting,setConnecting]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const editable=role==="owner"||role==="admin";
  const dirty=Boolean(settings&&brand&&JSON.stringify(brand)!==JSON.stringify(settings.branding));

  useEffect(()=>{
    let current=true;
    setLoading(true);setSettings(null);setIntegration(null);
    setBrand(null);setError("");setNotice("");
    Promise.all([
      merchantApi.getTenantSettings(tenantId),
      merchantApi.nuvemshopStatus(tenantId).catch(()=>null)
    ]).then(([prefs,link])=>{
      if(!current)return;
      setSettings(prefs);setBrand(prefs.branding);setIntegration(link);
    }).catch(cause=>{
      if(current)setError(fallbackError(cause,"Não foi possível carregar as configurações."));
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
      setNotice(result.updated?"Identidade salva. A página pública usará os novos dados quando for habilitada.":"Nenhuma alteração necessária.");
    }catch(cause){
      setError(fallbackError(cause,"Não foi possível salvar as configurações."));
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
      setError(fallbackError(cause,"Não foi possível iniciar a autorização da Nuvemshop."));
      setConnecting(false);
    }
  };

  if(loading)return <section className="ss-loading" role="status">
    <RefreshCw size={20} className="portal-spin"/> Consultando configurações da loja…
  </section>;
  if(!settings||!brand)return <section className="ss-feedback ss-error" role="alert">
    {error||"Configurações indisponíveis."}
  </section>;
  const status=integration?.customer_matching;
  const connected=Boolean(integration?.connected);
  const previewReady=Boolean(status?.read_only_preview_available);
  const programName=brand.program_name||("Clube "+settings.tenant_name);
  const programColor=/^#[0-9A-Fa-f]{6}$/.test(brand.primary_color)?brand.primary_color:"#087F79";
  const accent=/^#[0-9A-Fa-f]{6}$/.test(brand.accent_color)?brand.accent_color:"#37D5BB";

  return <div className="ss-root">
    <div className="ss-intro">
      <div className="ss-intro-icon"><Settings2 size={23}/></div>
      <div><span className="portal-eyebrow">CONTROLE DA SUA LOJA</span>
        <h2>Configurações</h2>
        <p>Personalize a experiência dos seus clientes e acompanhe as conexões do seu programa.</p>
      </div>
    </div>
    {error&&<div className="ss-feedback ss-error" role="alert"><TriangleAlert size={17}/>{error}</div>}
    {notice&&<div className="ss-feedback ss-success" role="status"><Check size={17}/>{notice}</div>}
    <div className="ss-layout">
      <section className="ss-card" aria-labelledby="ss-brand-title">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><Palette size={21}/></div>
          <div><h3 id="ss-brand-title">Identidade do programa</h3>
            <p>Como sua loja será apresentada aos participantes.</p></div>
          <Status ready={true} label="Configurável"/>
        </div>
        <div className="ss-brand-layout">
          <form className="ss-form" onSubmit={save}>
            <label>Nome do programa
              <input value={brand.program_name}
                onChange={e=>update("program_name",e.target.value)} maxLength={80}
                disabled={!editable||saving} placeholder={"Clube "+settings.tenant_name}/>
              <small>Deixe vazio para usar o nome padrão da loja.</small>
            </label>
            <div className="ss-color-grid">
              <label>Cor principal
                <div className="ss-color-control">
                  <input type="color" value={programColor}
                    disabled={!editable||saving}
                    onChange={e=>update("primary_color",e.target.value)}/>
                  <span>{brand.primary_color}</span>
                </div>
                <small>Utilizada em botões; deve oferecer contraste.</small>
              </label>
              <label>Cor de destaque
                <div className="ss-color-control">
                  <input type="color" value={accent}
                    disabled={!editable||saving}
                    onChange={e=>update("accent_color",e.target.value)}/>
                  <span>{brand.accent_color}</span>
                </div>
                <small>Para detalhes decorativos.</small>
              </label>
            </div>
            <label>E-mail de atendimento do programa
              <input value={brand.support_email}
                onChange={e=>update("support_email",e.target.value)}
                disabled={!editable||saving} maxLength={254}
                type="email" autoComplete="off" placeholder="atendimento@sualoja.com.br"/>
              <small>Informação de contato, não altera o remetente SMTP da Vidalys.</small>
            </label>
            {editable&&<div className="ss-action-row">
              <span>Versão {settings.version} · Alterações registradas</span>
              <button className="portal-primary" disabled={!dirty||saving} type="submit">
                <Save size={16}/>{saving?"Salvando…":"Salvar identidade"}
              </button>
            </div>}
            {!editable&&<p className="ss-readonly">Seu perfil pode visualizar, mas não modificar essas preferências.</p>}
          </form>
          <aside className="ss-live-card" aria-label="Prévia da identidade do programa">
            <div className="ss-preview-stage" style={{background:programColor}}>
              <div className="ss-preview-icon" style={{background:accent}}><HeartHandshake size={21}/></div>
              <span>PRÉVIA PARA O CONSUMIDOR</span>
              <strong>{programName}</strong>
              <p>Uma relação que vale mais. Conheça o programa da sua loja.</p>
              <div className="ss-preview-button">Conhecer regras e benefícios <ArrowRight size={16}/></div>
            </div>
            <div className="ss-preview-caption"><ShieldCheck size={15}/>
              Identidade em prévia. Nenhuma inscrição foi publicada.
            </div>
          </aside>
        </div>
      </section>
      <section className="ss-card" aria-labelledby="ss-integrations">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><Cloud size={21}/></div>
          <div><h3 id="ss-integrations">Integrações</h3>
            <p>Status das conexões autorizadas, sem expor credenciais.</p></div>
        </div>
        <div className="ss-integration">
          <div className="ss-service-label"><span className="ss-service-icon"><Cloud size={20}/></span>
            <div><strong>Nuvemshop</strong><small>Produtos e cadastro de clientes</small></div></div>
          <Status ready={connected} label={connected?"Instalação vinculada":"Conexão pendente"}/>
        </div>
        <div className="ss-connection-info">
          <div><small>Identificador da loja</small><strong>{integration?.store_id||"Não informado"}</strong></div>
          <div><small>Permissões do token instalado</small>
            <strong>{integration?.scope||"Não identificadas"}</strong></div>
          <div><small>Prévia de clientes</small>
            <strong>{previewReady?"Autorizada para leitura":status?.customer_scope_granted
              ?"Escopo presente; recurso bloqueado no servidor"
              :"Aguardando token com read_customers e liberação do recurso"}</strong></div>
        </div>
        {editable&&<button type="button" className="ss-secondary" onClick={()=>void reconnect()}
          disabled={connecting||!integration?.configured}>
          <RefreshCw size={16}/>{connecting?"Iniciando…":connected?"Reautorizar Nuvemshop":"Conectar Nuvemshop"}
          <ArrowRight size={15}/>
        </button>}
        {!integration?.configured&&<p className="ss-muted">OAuth indisponível até configurar o aplicativo no ambiente do servidor.</p>}
        <div className="ss-divider"/>
        <div className="ss-integration">
          <div className="ss-service-label"><span className="ss-service-icon"><Mail size={20}/></span>
            <div><strong>SMTP2GO · Vidalys</strong><small>Confirmação de e-mail e retirada do programa</small></div></div>
          <Status ready={settings.features.email_delivery_enabled}
            label={settings.features.email_delivery_enabled?"Habilitado no servidor":"Envio bloqueado"}/>
        </div>
        <p className="ss-muted">O status indica apenas a configuração de envio, não garante entrega. O remetente é configurado pela Vidalys, nunca pelo lojista.</p>
      </section>
      <section className="ss-card" aria-labelledby="ss-program-title">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><BookOpen size={20}/></div>
          <div><h3 id="ss-program-title">Programa e consentimento</h3>
            <p>Termos, privacidade e regras para entrada de participantes.</p></div>
        </div>
        <div className="ss-config-row"><div>
            <strong>Cadastro de participantes</strong>
            <p>A liberação depende de regulamento aprovado e confirmação de identidade.</p>
          </div>
          <Status ready={settings.features.public_signup_enabled}
            label={settings.features.public_signup_enabled?"Habilitado no servidor":"Bloqueado"}/>
        </div>
        <div className="ss-config-row"><div>
            <strong>Cashback e resgates</strong>
            <p>Continuam indisponíveis até haver pedidos pagos e resgate auditável.</p>
          </div>
          <Status ready={false} label="Não ativo"/>
        </div>
        <button type="button" className="ss-secondary" onClick={onGoToClients}>
          <BookOpen size={16}/> Gerenciar regulamento e aceites <ArrowRight size={15}/>
        </button>
      </section>
      <section className="ss-card" aria-labelledby="ss-domains-title">
        <div className="ss-card-heading">
          <div className="ss-card-icon"><Globe2 size={20}/></div>
          <div><h3 id="ss-domains-title">Endereço da sua loja</h3>
            <p>O cliente acessará seu programa em uma página própria.</p></div>
          <Status ready={false} label="Em desenvolvimento"/>
        </div>
        <div className="ss-domain">
          <div><small>Página de adesão planejada</small>
            <strong>{window.location.origin+"/participar/"+settings.tenant_slug}</strong></div>
          <div><small>Domínio personalizado</small>
            <strong>fideliza.sualoja.com.br</strong></div>
        </div>
        <div className="ss-advisory"><LockKeyhole size={16}/>
          Domínios próprios exigem verificação DNS e certificado SSL. Nenhum domínio
          está ativado por esta tela; não é necessário alterar o DNS agora.
        </div>
      </section>
    </div>
    <div className="ss-security-note"><ShieldCheck size={18}/>
      Preferências da loja não modificam estoque, pedidos, preços nem permissões
      da Nuvemshop. Cada alteração é vinculada ao usuário administrador e à versão salva.
    </div>
  </div>;
}
