import {useEffect,useRef,useState,type FormEvent} from "react";
import {Check,CircleHelp,Copy,Download,ExternalLink,FileText,LockKeyhole,Mail,MessageCircle,Monitor,
 RefreshCw,ShieldCheck,ShoppingBag,TriangleAlert,X} from "lucide-react";
import {ApiError,merchantApi,type NuvemshopConnectionStatus,type ProgramTermsStatus,
 type Store,type TenantBranding,type TenantPreferences,type PrivacyRequestsSummary} from "./api";
import {readableForeground} from "./brand-contrast";
import {initialsOf} from "./ActionCenter";
import "./vf-ui.css";
import "./store-settings.css";

/* Configurações — réplica do protótipo aprovado: menu de seções à esquerda e uma
   seção por vez. Aparência, Canais de venda, Página do clube, Equipe e acessos,
   Regulamento e privacidade, Ferramentas avançadas. Nada aqui muda preços,
   estoque ou pedidos da loja; status sem resposta da API fica "não verificado". */

export type SettingsSection="aparencia"|"canais"|"pagina"|"equipe"|"privacidade"|"ferramentas";
type Props={
 tenantId:string;role:Store["role"];
 userName?:string;userEmail?:string;
 initialSection?:SettingsSection;
 onGoToProgram:()=>void;
 onOpenTool?:(tool:"margin"|"costs"|"catalog")=>void;
};
type Diag={key:string;label:string;state:"ok"|"todo"|"unknown"};

const SECTIONS:{key:SettingsSection;label:string;hint:string}[]=[
 {key:"aparencia",label:"Aparência",hint:"Nome, cores e prévia"},
 {key:"canais",label:"Canais de venda",hint:"Nuvemshop, balcão e WhatsApp"},
 {key:"pagina",label:"Página do clube",hint:"Link e cadastro"},
 {key:"equipe",label:"Equipe e acessos",hint:"Quem faz o quê"},
 {key:"privacidade",label:"Regulamento e privacidade",hint:"Regras e LGPD"},
 {key:"ferramentas",label:"Ferramentas avançadas",hint:"Margem e catálogo"},
];
const SWATCHES=[["Roxo Vidalys","#6A3DF0"],["Azul","#1F4FA8"],["Verde","#167A56"],["Vinho","#AD334B"],["Grafite","#24113F"]];
const roleLabel:Record<Store["role"],string>={owner:"Proprietário",admin:"Gerente",analyst:"Consulta"};

function since(iso:string|null|undefined){
 if(!iso)return null;const d=new Date(iso);
 return Number.isNaN(d.getTime())?null:d.toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"short"});
}
function nuvemshopChecks(status:NuvemshopConnectionStatus|null,live:"idle"|"running"|"verified"|"failed"):Diag[]{
 const known=status!==null;
 const f=(v:boolean|undefined):Diag["state"]=>v===undefined||!known?"unknown":v?"ok":"todo";
 const inbox=status?.order_verification?.signed_event_inbox_enabled;
 return [
  {key:"app",label:"App preparado",state:f(status?.configured)},
  {key:"store",label:"Loja autorizada",state:status?.uninstalled_at?"todo":f(status?.connected)},
  {key:"products",label:"Leitura de produtos",state:f(status?.connection_check?.catalog_scope_granted)},
  {key:"orders",label:"Leitura de pedidos",state:f(status?.order_verification?.order_scope_granted)},
  {key:"customers",label:"Leitura de clientes",state:f(status?.customer_matching?.customer_scope_granted)},
  {key:"events",label:"Avisos de pedidos",state:!known||!inbox?"unknown":status?.last_order_event_at?"ok":"todo"},
  {key:"live",label:"Acesso conferido agora",state:live==="verified"?"ok":live==="failed"?"todo":"unknown"},
 ];
}
function friendlyError(error:unknown,fallback:string){
 if(error instanceof ApiError){
  if(error.status===409)return "Essas informações mudaram. Atualize a página antes de tentar novamente.";
  if(error.status===403)return "Seu usuário não tem autorização para realizar esta ação.";
  if(error.status===429)return "Já houve uma tentativa recente. Tente novamente em alguns instantes.";
  if(error.status===503)return "Conexão temporariamente indisponível. Tente novamente mais tarde.";
 }
 return fallback;
}

export default function StoreSettings({tenantId,role,userName,userEmail,initialSection,onGoToProgram,onOpenTool}:Props){
 const editable=role==="owner"||role==="admin";
 const [section,setSection]=useState<SettingsSection>(initialSection??"aparencia");
 const [settings,setSettings]=useState<TenantPreferences|null>(null);
 const [integration,setIntegration]=useState<NuvemshopConnectionStatus|null>(null);
 const [terms,setTerms]=useState<ProgramTermsStatus|null>(null);
 const [privacy,setPrivacy]=useState<PrivacyRequestsSummary|null>(null);
 const [brand,setBrand]=useState<TenantBranding|null>(null);
 const [loading,setLoading]=useState(true);
 const [saving,setSaving]=useState(false);
 const [connecting,setConnecting]=useState(false);
 const [liveCheck,setLiveCheck]=useState<"idle"|"running"|"verified"|"failed">("idle");
 const [reportBusy,setReportBusy]=useState<string|null>(null);
 const [reportDownloads,setReportDownloads]=useState<Record<string,{digest:string;complete:boolean}>>({});
 const [copied,setCopied]=useState(false);
 const checkSequence=useRef(0);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const dirty=Boolean(settings&&brand&&JSON.stringify(brand)!==JSON.stringify(settings.branding));

 useEffect(()=>{
  let current=true;checkSequence.current++;
  setLiveCheck("idle");setLoading(true);setSettings(null);setIntegration(null);setPrivacy(null);setTerms(null);
  setReportDownloads({});setBrand(null);setError("");setNotice("");
  Promise.all([
   merchantApi.getTenantSettings(tenantId),
   merchantApi.nuvemshopStatus(tenantId).catch(()=>null),
   editable?merchantApi.getTenantPrivacyRequests(tenantId).catch(()=>null):Promise.resolve(null),
   editable?merchantApi.currentProgramTerms(tenantId).catch(()=>null):Promise.resolve(null),
  ]).then(([prefs,link,requests,currentTerms])=>{
   if(!current)return;
   setSettings(prefs);setBrand(prefs.branding);setIntegration(link);setPrivacy(requests);setTerms(currentTerms);
   const query=new URLSearchParams(window.location.search);
   const result=query.get("nuvemshop");
   if(result==="connected"||result==="failed"){
    setSection("canais");
    const sourceTenant=query.get("nuvemshop_tenant");
    query.delete("nuvemshop");query.delete("nuvemshop_tenant");
    const rest=query.toString();
    window.history.replaceState(null,"",window.location.pathname+(rest?"?"+rest:"")+window.location.hash);
    if(sourceTenant&&sourceTenant!==tenantId)setError("A autorização retornou para outra loja. Confira a loja selecionada.");
    else if(result==="failed")setError("A autorização não foi concluída. Tente novamente.");
    else if(link?.connected)setNotice("Autorização registrada. Verifique o acesso à Nuvemshop antes de usar o catálogo.");
    else setError("A autorização retornou, mas a conexão não foi confirmada. Atualize a página.");
   }
  }).catch(()=>{if(current)setError("Não foi possível carregar as configurações da loja.");})
   .finally(()=>{if(current)setLoading(false);});
  return()=>{current=false};
 },[tenantId,editable]);

 const pick=(next:SettingsSection)=>{setSection(next);setError("");setNotice("");};
 const update=(key:keyof TenantBranding,value:string)=>setBrand(old=>old?{...old,[key]:value}:old);
 const save=async(event:FormEvent)=>{
  event.preventDefault();
  if(!settings||!brand||!editable||!dirty||saving)return;
  setSaving(true);setError("");setNotice("");
  try{
   const result=await merchantApi.saveTenantBranding(tenantId,settings.version,brand);
   setSettings({...settings,branding:result.branding,version:result.version});setBrand(result.branding);
   setNotice(result.updated?"Aparência salva. O Meu Clube já usa o novo nome e as cores.":"Nada mudou: a aparência já estava assim.");
  }catch(e){setError(friendlyError(e,"Não foi possível salvar. Confira os campos e tente novamente."));}
  finally{setSaving(false);}
 };
 const reconnect=async()=>{
  if(!editable||connecting)return;
  setConnecting(true);setError("");setNotice("");
  try{
   const result=await merchantApi.beginNuvemshopOAuth(tenantId);
   const url=new URL(result.authorize_url);
   if(url.protocol!=="https:"||url.hostname!=="www.tiendanube.com"||!/^\/apps\/[0-9]+\/authorize$/.test(url.pathname))
    throw new Error("Endereço de autorização não reconhecido.");
   window.location.assign(url.toString());
  }catch(e){setError(friendlyError(e,"Não foi possível abrir a autorização da sua loja."));setConnecting(false);}
 };
 const verifyReadAccess=async()=>{
  if(!editable||!integration?.connected||settings?.tenant_status!=="active"||
   integration.connection_check?.catalog_scope_granted===false||liveCheck==="running")return;
  const sequence=++checkSequence.current;
  setLiveCheck("running");setError("");setNotice("");
  try{
   const preview=await merchantApi.previewLiveNuvemshop(tenantId,1);
   if(preview.source!=="nuvemshop_live_read_only"||preview.writes_performed!==0)throw new Error("Resposta inesperada");
   if(sequence!==checkSequence.current)return;
   setLiveCheck("verified");
   setNotice("Acesso de leitura confirmado agora. A Nuvemshop respondeu sem alterar produtos.");
  }catch(e){
   if(sequence!==checkSequence.current)return;
   setLiveCheck("failed");
   setError(friendlyError(e,"Não foi possível verificar o acesso. Confira a autorização da loja e tente novamente."));
  }
 };
 const downloadReport=async(requestId:string)=>{
  if(reportBusy)return;setReportBusy(requestId);setError("");setNotice("");
  try{
   const file=await merchantApi.downloadPrivacyReport(tenantId,requestId);
   if(!/^[0-9a-f]{64}$/.test(file.digest))throw new Error("Relatório sem comprovante válido.");
   const local=URL.createObjectURL(file.blob);const a=document.createElement("a");
   a.href=local;a.download="relatorio-fideliza-"+requestId+".json";document.body.appendChild(a);a.click();a.remove();
   window.setTimeout(()=>URL.revokeObjectURL(local),1000);
   setReportDownloads(old=>({...old,[requestId]:{digest:file.digest,complete:file.complete}}));
   setNotice(file.complete?"O arquivo foi preparado. Confira o conteúdo antes de confirmar o recebimento."
    :"O relatório parcial foi preparado. A Vidalys precisa revisar os dados antes de encerrar o pedido.");
  }catch(e){setError(friendlyError(e,"Não foi possível preparar o relatório. Tente novamente."));}
  finally{setReportBusy(null);}
 };
 const confirmReport=async(requestId:string)=>{
  const item=reportDownloads[requestId];if(!item?.complete||reportBusy)return;
  setReportBusy(requestId);setError("");setNotice("");
  try{
   const result=await merchantApi.confirmPrivacyReport(tenantId,requestId,item.digest);
   setPrivacy(old=>old?{...old,pending_total:Math.max(0,old.pending_total-1),access_requests:Math.max(0,old.access_requests-1),
    items:old.items.filter(e=>e.id!==requestId)}:old);
   setReportDownloads(old=>{const n={...old};delete n[requestId];return n;});
   setNotice(result.message);
  }catch(e){setError(friendlyError(e,"Não foi possível confirmar. Baixe novamente o relatório se os dados mudaram."));}
  finally{setReportBusy(null);}
 };

 const head=<div className="vf-head"><div><span className="vf-eyebrow">Configurações</span><h1 id="ss-title" className="vf-h1">Sua loja, do seu jeito</h1></div></div>;
 if(loading)return <section className="vf-screen ss-root" aria-labelledby="ss-title">{head}
  <p className="vf-muted" role="status"><RefreshCw size={18} className="portal-spin"/> Carregando suas configurações…</p></section>;
 if(!settings||!brand)return <section className="vf-screen ss-root" aria-labelledby="ss-title">{head}
  <div className="vf-toast is-error" role="alert">{error||"As configurações não estão disponíveis no momento."}</div></section>;

 const connected=Boolean(integration?.connected);
 const programName=brand.program_name||("Clube "+settings.tenant_name);
 const programColor=/^#[0-9A-Fa-f]{6}$/.test(brand.primary_color)?brand.primary_color:"#6A3DF0";
 const accent=/^#[0-9A-Fa-f]{6}$/.test(brand.accent_color)?brand.accent_color:"#FFC857";
 const clubUrl=window.location.origin+"/clube/"+encodeURIComponent(settings.tenant_slug);
 const checks=nuvemshopChecks(integration,liveCheck);
 const step=integration?.connection_check?.next_step;
 const nuvemshopText=liveCheck==="verified"?"Consulta real concluída agora, sem alterar a loja."
  :step==="activate_tenant"?"Sua loja precisa estar ativa para usar a integração."
  :step==="configure_app"?"O aplicativo ainda precisa ser configurado pela equipe Vidalys."
  :step==="reinstall_app"?`O aplicativo foi desinstalado${since(integration?.uninstalled_at)?" em "+since(integration?.uninstalled_at):""}. Reinstale para voltar a ler pedidos e produtos.`
  :step==="authorize_store"?"Autorize a conexão da sua loja pela Nuvemshop para começar."
  :step==="grant_read_products_and_reinstall"?"Falta permissão para ler produtos. Ajuste no Portal de Parceiros e reinstale o app."
  :step==="verify_catalog_with_live_get"?"Autorização registrada. Use \"Verificar acesso à Nuvemshop\" para confirmar."
  :!integration?.configured?"A conexão ainda está sendo preparada pela plataforma.":connected?"Autorização registrada para esta loja.":"Loja ainda não conectada.";
 const chipFor=(c:Diag)=>c.state==="ok"?"is-ok":c.state==="todo"?"is-gold":"is-soft";
 const copyLink=async()=>{
  try{await navigator.clipboard.writeText(clubUrl);setCopied(true);window.setTimeout(()=>setCopied(false),2000);}
  catch{setError("Não foi possível copiar. Selecione o endereço e copie manualmente.");}
 };

 return <section className="vf-screen ss-root" aria-labelledby="ss-title">
  {head}
  {error&&<div className="vf-toast is-error" role="alert"><TriangleAlert size={18}/>{error}</div>}
  {notice&&<div className="vf-toast" role="status"><Check size={18}/>{notice}</div>}
  <div className="ss-layout">
   <nav className="vf-card ss-menu" aria-label="Seções das configurações">
    {SECTIONS.filter(s=>s.key!=="ferramentas"||onOpenTool).filter(s=>s.key!=="privacidade"||editable).map(s=>
     <button key={s.key} type="button" className={"vf-tab ss-menu-item"+(section===s.key?" is-on":"")}
      aria-current={section===s.key?"page":undefined} onClick={()=>pick(s.key)}>
      <span>{s.label}</span><small>{s.hint}</small></button>)}
   </nav>
   <div className="ss-panel">

    {section==="aparencia"&&<form className="vf-card ss-section" onSubmit={save} aria-labelledby="ss-brand-title">
     <div className="vf-card-head"><div><h2 id="ss-brand-title" className="vf-h2">Aparência do clube</h2>
      <span className="vf-muted vf-small">O que o cliente vê no Meu Clube e nos e-mails.</span></div></div>
     <div className="vf-grid2">
      <label className="vf-field">Nome do programa
       <input value={brand.program_name} maxLength={80} disabled={!editable||saving} placeholder={"Clube "+settings.tenant_name}
        onChange={e=>update("program_name",e.target.value)}/></label>
      <label className="vf-field">E-mail de atendimento
       <input type="email" value={brand.support_email} maxLength={254} autoComplete="off" disabled={!editable||saving}
        placeholder="atendimento@sualoja.com.br" onChange={e=>update("support_email",e.target.value)}/></label>
     </div>
     {(["primary_color","accent_color"] as const).map(key=><div key={key} className="ss-colors">
      <span className="ss-label">{key==="primary_color"?"Cor principal":"Cor de destaque"}</span>
      <div className="ss-swatches" role="group" aria-label={key==="primary_color"?"Cor principal":"Cor de destaque"}>
       {(key==="primary_color"?SWATCHES:[["Dourado","#FFC857"],["Laranja","#FF8A3D"],["Lavanda","#EDE7FF"],["Verde-claro","#BFE8D3"],["Branco","#FFFFFF"]]).map(([name,hex])=>{
        const on=brand[key].toUpperCase()===hex;
        return <button key={hex} type="button" className={"ss-swatch"+(on?" is-on":"")} aria-label={name} aria-pressed={on}
         disabled={!editable||saving} style={{background:hex}} onClick={()=>update(key,hex)}/>;})}
       <label className="ss-swatch-custom">Outra cor
        <input type="color" value={key==="primary_color"?programColor:accent} disabled={!editable||saving}
         onChange={e=>update(key,e.target.value.toUpperCase())}/></label>
      </div>
     </div>)}
     <div className="ss-logo">
      <span className="vf-avatar ss-logo-mark" style={{background:accent,color:readableForeground(accent)}} aria-hidden="true">{initialsOf(settings.tenant_name)}</span>
      <div className="vf-row-main"><strong>Logo da loja</strong><span>Por enquanto o clube usa as iniciais da loja na cor de destaque.</span></div>
      <span className="vf-chip is-soft">Envio de logo em breve</span>
     </div>
     <div className="ss-preview-wrap"><span className="ss-label">Prévia no celular do cliente</span>
      <div className="ss-phone" style={{background:`linear-gradient(135deg, ${programColor}, color-mix(in srgb, ${programColor} 70%, black))`,color:readableForeground(programColor)}}>
       <span className="ss-phone-name">{programName.toUpperCase()}</span>
       <strong>340 pontos</strong>
       <span>Exemplo de saldo · como o cliente vai ver</span>
       <span className="ss-phone-btn" style={{background:accent,color:readableForeground(accent)}}>Ver recompensas</span>
      </div>
     </div>
     {editable?<div className="ss-actions"><button type="submit" className="vf-btn is-primary" disabled={!dirty||saving}>{saving?"Salvando…":"Salvar aparência"}</button></div>
      :<p className="vf-note">Você pode consultar estas opções. Um administrador da loja pode alterá-las.</p>}
    </form>}

    {section==="canais"&&<section className="vf-card ss-section" aria-labelledby="ss-store-connection">
     <div className="vf-card-head"><div><h2 id="ss-store-connection" className="vf-h2">Canais de venda</h2>
      <span className="vf-muted vf-small">Onde o cliente compra e ganha pontos.</span></div></div>
     <div className="vf-row is-top ss-channel">
      <span className="vf-ico tone-purple" aria-hidden="true"><ShoppingBag size={20}/></span>
      <div className="vf-row-main">
       <div className="ss-channel-title"><strong>Nuvemshop</strong>
        <span className={"vf-chip "+(connected?(liveCheck==="verified"?"is-ok":"is-soft"):"is-gold")}>{connected?(liveCheck==="verified"?"Acesso verificado":"Autorização registrada"):"Não vinculada"}</span></div>
       <span>{nuvemshopText}</span>
       <ul className="ss-checks" aria-label="Diagnóstico da conexão Nuvemshop">
        {checks.map(c=><li key={c.key} className={"vf-chip "+chipFor(c)}>
         {c.state==="ok"?<Check size={13}/>:c.state==="todo"?<LockKeyhole size={13}/>:<CircleHelp size={13}/>}{c.label}
         <span className="vf-sr">{c.state==="ok"?": ok":c.state==="todo"?": pendente":": não verificado"}</span></li>)}
       </ul>
       {editable&&<div className="ss-channel-actions">
        <button type="button" className="vf-btn is-small is-primary" disabled={connecting||!integration?.configured} onClick={()=>void reconnect()}>
         {connecting?"Abrindo sua loja…":connected?"Atualizar conexão":"Conectar minha loja"}</button>
        {connected&&integration?.connection_check?.catalog_scope_granted!==false&&settings.tenant_status==="active"&&
         <button type="button" className="vf-btn is-small" disabled={liveCheck==="running"} onClick={()=>void verifyReadAccess()}>
          {liveCheck==="running"?"Conferindo acesso…":liveCheck==="verified"?"Conferir acesso novamente":"Verificar acesso à Nuvemshop"}</button>}
       </div>}
       {editable&&connected&&<span role="status" aria-live="polite">{liveCheck==="verified"?"Acesso verificado agora. Vale só para esta sessão."
        :liveCheck==="failed"?"Acesso não verificado. A autorização pode precisar ser atualizada."
        :liveCheck==="running"?"Consultando a Nuvemshop sem modificar seus produtos…"
        :"A autorização salva ainda não comprova acesso atual. Faça uma consulta de leitura."}</span>}
      </div>
     </div>
     <div className="vf-row is-top">
      <span className="vf-ico tone-gold" aria-hidden="true"><Monitor size={20}/></span>
      <div className="vf-row-main"><strong>Balcão da loja física</strong><span>Venda pelo painel em "Registrar venda", com conferência. Sempre disponível.</span></div>
      <span className="vf-chip is-ok">Ativo</span>
     </div>
     <div className="vf-row is-top">
      <span className="vf-ico tone-green" aria-hidden="true"><MessageCircle size={20}/></span>
      <div className="vf-row-main"><strong>WhatsApp</strong><span>Mensagens prontas de saldo e vencimento para você enviar.</span></div>
      <span className="vf-chip is-soft">Em breve</span>
     </div>
     <div className="vf-row is-top">
      <span className="vf-ico tone-purple" aria-hidden="true"><Mail size={20}/></span>
      <div className="vf-row-main"><strong>Confirmação por e-mail</strong><span>O cliente confirma a adesão e acessa o Meu Clube com segurança.</span></div>
      <span className={"vf-chip "+(settings.features.email_delivery_enabled?"is-ok":"is-gold")}>{settings.features.email_delivery_enabled?"Configurada":"Em preparação"}</span>
     </div>
     <div className="vf-row is-top">
      <span className="vf-ico tone-rose" aria-hidden="true"><ShieldCheck size={20}/></span>
      <div className="vf-row-main"><strong>Pontos de verdade</strong><span>Liberação feita pela equipe Vidalys, loja a loja, depois de homologar pagamentos.</span></div>
      <span className={"vf-chip "+(settings.features.loyalty_live_enabled?"is-ok":"is-soft")}>{settings.features.loyalty_live_enabled?"Piloto autorizado":"Desligado"}</span>
     </div>
    </section>}

    {section==="pagina"&&<section className="vf-card ss-section" aria-labelledby="ss-domains-title">
     <div className="vf-card-head"><div><h2 id="ss-domains-title" className="vf-h2">Página do clube</h2>
      <span className="vf-muted vf-small">O endereço onde o cliente entra, confere saldo e troca pontos.</span></div></div>
     <label className="vf-field">Endereço do Meu Clube<input readOnly value={clubUrl} onFocus={e=>e.currentTarget.select()}/></label>
     <div className="vf-pills">
      <button type="button" className="vf-btn" onClick={()=>void copyLink()}><Copy size={16}/>{copied?"Link copiado":"Copiar link"}</button>
      <a className="vf-btn" href={"/clube/"+encodeURIComponent(settings.tenant_slug)} target="_blank" rel="noopener noreferrer"><ExternalLink size={16}/> Abrir página do cliente</a>
     </div>
     <div className="vf-row"><span className={"vf-chip "+(settings.features.public_signup_enabled?"is-ok":"is-gold")}>{settings.features.public_signup_enabled?"Ligado":"Desligado"}</span>
      <span className="vf-row-main"><strong>Cadastro aberto ao público</strong><span>{settings.features.public_signup_enabled?"Pode ser divulgado depois de aprovar o regulamento.":"Liberação feita pela equipe Vidalys."}</span></span></div>
     <div className="vf-row"><span className="vf-chip is-soft">Em breve</span><span className="vf-row-main"><strong>Domínio próprio</strong><span>clube.sualoja.com.br</span></span></div>
     <div className="ss-actions"><button type="button" className="vf-btn" onClick={onGoToProgram}>Gerenciar regulamento e convites</button></div>
    </section>}

    {section==="equipe"&&<section className="vf-card ss-section" aria-labelledby="ss-team-title">
     <div className="vf-card-head"><div><h2 id="ss-team-title" className="vf-h2">Equipe e acessos</h2>
      <span className="vf-muted vf-small">Quem pode vender, conferir e mudar o clube.</span></div>
      <span className="vf-chip is-soft">Convites em breve</span></div>
     <div className="vf-row"><span className="vf-avatar tone-1" aria-hidden="true">{initialsOf(userName)}</span>
      <div className="vf-row-main"><strong>{userName||"Você"}</strong><span>{userEmail||"Conta conectada agora"}</span></div>
      <span className="vf-chip is-gold">{roleLabel[role]}</span></div>
     <div className="vf-note ss-roles"><span><strong>Proprietário:</strong> tudo, incluindo integrações e equipe.</span>
      <span><strong>Gerente:</strong> regras, recompensas, campanhas e conferência de vendas.</span>
      <span><strong>Consulta:</strong> acompanha clientes, vendas e resultados, sem alterar.</span></div>
    </section>}

    {section==="privacidade"&&editable&&<section className="vf-card ss-section" aria-labelledby="ss-privacy-title">
     <div className="vf-card-head"><div><h2 id="ss-privacy-title" className="vf-h2">Regulamento e privacidade</h2>
      <span className="vf-muted vf-small">Regras claras e LGPD em dia.</span></div></div>
     <div className="vf-row is-wrap">
      <span className={"vf-chip "+(terms?.terms?"is-ok":"is-gold")}>{terms===null?"Não verificado":terms.terms?"Aprovado":"Pendente"}</span>
      <span className="vf-row-main"><strong>Regulamento do clube</strong><span>{terms?.terms?`Versão ${terms.terms.version}, aprovada.`:"Aprove antes de convidar clientes."}</span></span>
      <button type="button" className="vf-btn is-small" onClick={onGoToProgram}>{terms?.terms?"Ver regulamento":"Aprovar regulamento"}</button>
     </div>
     <div className="vf-row is-wrap">
      <span className="vf-chip is-soft">{privacy?`${privacy.pending_total} pendente${privacy.pending_total===1?"":"s"}`:"Não verificado"}</span>
      <span className="vf-row-main"><strong>Pedidos de clientes</strong><span>{privacy?`${privacy.access_requests} de acesso aos dados · ${privacy.deletion_requests} de exclusão`:"Não foi possível consultar agora."}</span></span>
     </div>
     {privacy?.items.length?<ul className="vf-list">{privacy.items.map(item=><li key={item.id} className="vf-row is-top is-wrap">
      <span className="vf-ico tone-purple" aria-hidden="true"><FileText size={18}/></span>
      <div className="vf-row-main"><strong>{item.type==="data_access"?"Pedido de acesso aos dados":"Pedido de exclusão de dados"}</strong>
       <span>Recebido em {new Date(item.received_at).toLocaleDateString("pt-BR")} · em análise
        {item.type==="deletion"?(item.protection_applied?" · contato já protegido":" · proteção em andamento"):""}</span>
       {reportDownloads[item.id]&&!reportDownloads[item.id].complete&&<span>O relatório precisa de revisão para concluir o pedido.</span>}</div>
      {item.report_available&&<div className="ss-channel-actions">
       <button type="button" className="vf-btn is-small" disabled={reportBusy!==null} onClick={()=>void downloadReport(item.id)}>
        <Download size={15}/>{reportBusy===item.id?"Preparando…":"Baixar relatório"}</button>
       {reportDownloads[item.id]?.complete&&<button type="button" className="vf-btn is-small is-primary" disabled={reportBusy!==null}
        onClick={()=>void confirmReport(item.id)}><Check size={15}/>Confirmar que recebi</button>}
      </div>}
     </li>)}</ul>:null}
     <p className="vf-note"><ShieldCheck size={16}/>O cliente faz o pedido à loja. A Vidalys protege os dados mantidos no Fideliza e acompanha a eliminação; registros com retenção legal passam por análise.</p>
    </section>}

    {section==="ferramentas"&&onOpenTool&&<section className="vf-card ss-section" aria-labelledby="ss-tools-title">
     <div className="vf-card-head"><div><h2 id="ss-tools-title" className="vf-h2">Ferramentas avançadas</h2>
      <span className="vf-muted vf-small">Para conferir margem e catálogo. Não são necessárias no dia a dia.</span></div></div>
     {([["margin","Custo dos benefícios","Quanto cada recompensa custa na sua margem.","Abrir custo dos benefícios"],
       ["costs","Custos dos produtos","Custo por produto quando a loja não informa.","Abrir custos dos produtos"],
       ["catalog","Conciliação do catálogo","Confere variantes da Nuvemshop antes de importar custos.","Abrir conciliação"]] as const).map(([tool,title,detail,action])=>
      <div key={tool} className="vf-row is-wrap"><span className="vf-row-main"><strong>{title}</strong><span>{detail}</span></span>
       <button type="button" className="vf-btn is-small" aria-label={action} onClick={()=>onOpenTool(tool)}>Abrir</button></div>)}
    </section>}

    {!editable&&section==="privacidade"&&<div className="vf-toast is-info"><X size={18}/>Seção disponível para administradores.</div>}
   </div>
  </div>
 </section>;
}
