import {useEffect,useState,type FormEvent} from "react";
import {
  ArrowRight,BookOpen,Check,CheckCircle2,Globe2,HeartHandshake,
  LockKeyhole,Mail,Palette,RefreshCw,Save,Settings2,ShieldCheck,TriangleAlert,ShoppingBag
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
function friendlyError(error:unknown,defaultMessage:string){
  // Esconder detalhes técnicos de falhas de integração do painel do lojista.
  if(error instanceof ApiError){
    if(error.status===409)return "Esta opção ainda não está pronta para sua loja. Tente novamente mais tarde.";
    if(error.status===403)return "Seu usuário não tem autorização para realizar esta ação.";
    if(error.status===429)return "Já houve uma tentativa recente. Tente novamente em alguns instantes.";
    if(error.status===503)return "Conexão temporariamente indisponível. Tente novamente mais tarde.";
  }
  return defaultMessage;
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

  if(loading)return <section className="ss-loading" role="status">
    <RefreshCw size={20} className="portal-spin"/> Carregando suas preferências…
  </section>;
  if(!settings||!brand)return <section className="ss-feedback ss-error" role="alert">
    {error||"As configurações não estão disponíveis no momento."}
  </section>;
  const connected=Boolean(integration?.connected);
  const customerReady=Boolean(integration?.customer_matching?.read_only_preview_available);
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
            <div className="ss-preview-stage" style={{background:programColor}}>
              <div className="ss-preview-icon" style={{background:accent}}><HeartHandshake size={21}/></div>
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
          <Status ready={connected} label={connected?"Conectada":"Não conectada"}/>
        </div>
        <p className="ss-muted">{!connected
          ?"Conecte sua loja para consultar as informações necessárias ao programa."
          :customerReady
            ?"A conexão está pronta para conferir cadastros de clientes que autorizaram participar."
            :"A loja está conectada. A consulta de participantes ainda está em preparação."}</p>
        {editable&&<button type="button" className="ss-secondary" onClick={()=>void reconnect()}
          disabled={connecting||!integration?.configured}>
          <RefreshCw size={16}/>{connecting?"Abrindo sua loja…":connected?"Atualizar conexão":"Conectar minha loja"}
          <ArrowRight size={15}/>
        </button>}
        {editable&&!integration?.configured&&<p className="ss-muted">
          A conexão estará disponível assim que a plataforma concluir a preparação da sua loja.</p>}
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
        <button type="button" className="ss-secondary" onClick={onGoToClients}>
          <BookOpen size={16}/> Editar regras e adesão <ArrowRight size={15}/>
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
    </div>
    <div className="ss-security-note"><ShieldCheck size={18}/>
      Alterar seu clube aqui não muda preços, estoque nem pedidos da sua loja.
    </div>
  </div>;
}
