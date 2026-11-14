import {useState} from "react";
import {Award, Check, Clock3, Gift, LockKeyhole, Sparkles, TicketPercent} from "lucide-react";
import {ApiError, publicEnrollmentApi, type MemberClubPrivate} from "./api";
import "./member-overview.css";

const currency=(cents:number)=>new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(cents/100);

export function MemberVipCard({me}:{me:MemberClubPrivate}){
  const current=me.vip_level||null;
  const next=me.vip_next_level||null;
  const progress=me.vip_progress_percent;
  const hasProgress=current!==null&&typeof progress==="number"
    &&Number.isFinite(progress)&&progress>=0&&progress<=100;
  return <section className="mc-vip" aria-label="Meu nível VIP">
    <div className="mc-vip-intro">
      <span className="mc-vip-medal" aria-hidden="true"><Award size={23}/></span>
      <div><span className="mc-overview-kicker">MEU NÍVEL VIP</span>
        <h2>{current||"Níveis em preparação"}</h2>
      </div>
      <span className="mc-vip-tag">{current?"Seu nível":"Aguardando ativação"}</span>
    </div>
    <div className="mc-vip-progress" role={hasProgress?"progressbar":undefined}
      aria-label={hasProgress?"Progresso para o próximo nível VIP":undefined}
      aria-valuemin={hasProgress?0:undefined} aria-valuemax={hasProgress?100:undefined}
      aria-valuenow={hasProgress?progress:undefined}>
      <span style={{width:hasProgress?progress+"%":"0%"}}/>
    </div>
    <p>{current
      ?next?"Seu progresso até "+next+": "+(progress??"—")+"%.":"Você está no nível mais alto disponível."
      :"O nível aparecerá quando a loja ativar regras VIP verificadas. Não exibimos progresso fictício."}</p>
  </section>;
}

export function MemberWalletOverview({me,pointsReady,ledgerOnly}:{
  me:MemberClubPrivate;pointsReady:boolean;ledgerOnly:boolean;
}){
  const points=me.points_balance;
  const cashback=me.cashback_balance_cents;
  const hasCashback=typeof cashback==="number"&&Number.isFinite(cashback);
  return <section className="member-club-wallet member-club-panel" aria-label="Resumo da minha carteira">
    <div className="member-club-wallet-main">
      <div className="member-club-wallet-heading">
        <span className="member-club-kicker"><Gift size={16}/> MINHA CARTEIRA</span>
        {!pointsReady&&<span className="member-club-wallet-pending"><Clock3 size={13}/>
          {ledgerOnly?"Saldo em conferência":"Em preparação"}</span>}
      </div>
      <div className="mc-balance-grid">
        <div className="mc-balance-amount">
          <span className="member-club-wallet-label">
            {ledgerOnly?"Pontos internos, sem resgate":"Pontos disponíveis"}</span>
          <strong className="member-club-wallet-number">
            {typeof points==="number"?points.toLocaleString("pt-BR"):"—"}
            {typeof points==="number"&&<small>pontos</small>}
          </strong>
        </div>
        <div className="mc-balance-amount mc-balance-cashback">
          <span className="member-club-wallet-label">Cashback (R$)</span>
          <strong className="mc-cashback-number">{hasCashback?currency(cashback):"—"}</strong>
          <small>{hasCashback?"Saldo interno, sem uso liberado":"Ainda indisponível"}</small>
        </div>
      </div>
      <p>{pointsReady?"Acompanhe suas compras e os benefícios realmente liberados pela loja."
        :ledgerOnly?"Os lançamentos internos estão registrados, mas não podem ser trocados por descontos até a conciliação de pagamentos e a ativação do resgate."
        :"O clube ainda não liberou a pontuação. Nenhum saldo foi atribuído."}</p>
    </div>
    {(pointsReady||ledgerOnly)&&<div className="member-club-wallet-aside">
      <div><Clock3 size={18}/><span>Pendentes</span>
        <strong>{me.points_pending!==null?me.points_pending.toLocaleString("pt-BR"):"—"}</strong>
      </div>
      <div><Gift size={18}/><span>A vencer</span>
        <strong>{me.points_expiring!==null?me.points_expiring.toLocaleString("pt-BR"):"—"}</strong>
      </div>
    </div>}
  </section>;
}

type VoucherResponse={code:string;voucher_id:string;discount_cents:number;expires_at:string;external_coupon_created:false};

export function MemberRedeemAction({slug,me,rewardPoints}:{
  slug:string;me:MemberClubPrivate;rewardPoints:number|null;
}){
  const [busy,setBusy]=useState(false);
  const [issued,setIssued]=useState<VoucherResponse|null>(null);
  const [message,setMessage]=useState("");
  const canRedeem=me.redemption_enabled&&me.points_status==="verified"
    &&typeof me.points_balance==="number"&&rewardPoints!==null
    &&me.points_balance>=rewardPoints;
  const generate=async()=>{
    if(!canRedeem||rewardPoints===null||busy)return;
    setBusy(true);setMessage("");
    try{
      setIssued(await publicEnrollmentApi.clubIssueVoucher(slug,"points",rewardPoints));
    }catch(cause){
      setMessage(cause instanceof ApiError?cause.message:
        "Não foi possível gerar o voucher. Confira o saldo e tente novamente.");
    }finally{setBusy(false)}
  };
  return <section className="mc-redeem" aria-label="Resgate rápido">
    <div className="mc-redeem-copy">
      <span className="mc-overview-kicker"><TicketPercent size={16}/> RESGATE RÁPIDO</span>
      <h2>Troque pontos por um benefício</h2>
      <p>{canRedeem?"Gere seu voucher individual e confira como usá-lo na loja.":
        "A emissão está bloqueada até que a loja habilite o resgate e confirme os saldos."}</p>
    </div>
    <div className="mc-redeem-action">
      <button type="button" disabled={!canRedeem||busy} onClick={()=>void generate()}>
        {canRedeem?<TicketPercent size={18}/>:<LockKeyhole size={18}/>}
        {busy?"Gerando…":"Gerar voucher"}
      </button>
      {!canRedeem&&<small>Não há benefício disponível para emissão neste momento.</small>}
    </div>
    {issued&&<div className="mc-issued-voucher" role="status">
      <strong>Voucher interno gerado: <code>{issued.code}</code></strong>
      <p>Guarde o código: ele é mostrado uma única vez. O uso depende da integração do canal; nenhum cupom Nuvemshop foi criado.</p>
    </div>}
    {message&&<p className="mc-redeem-error" role="alert">{message}</p>}
  </section>;
}

export function MemberMissions({me}:{me:MemberClubPrivate}){
  const missions=me.missions||[];
  return <section className="mc-missions" aria-label="Missões do clube">
    <div><span className="mc-overview-kicker"><Sparkles size={16}/> ENGAJAMENTO</span>
      <h2>Missões do clube</h2></div>
    {missions.length?<ul>{missions.map(mission=><li key={mission.id}>
      <Check size={15}/>{mission.title}
      <span>{mission.state==="eligible"?"Elegível, sem bônus liberado":"Em preparação"}</span>
    </li>)}</ul>:<p>Missões e bônus de aniversário aparecerão aqui após a ativação. Nenhum ponto extra foi concedido.</p>}
  </section>;
}
