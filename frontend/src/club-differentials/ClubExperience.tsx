import {useState} from "react";
import {Award, Check, Clock3, Gift, Info, Link2, LockKeyhole, Sparkles} from "lucide-react";
import {brl, dateBR, days, points, whatsappShareUrl} from "./format";
import type {ClubInsights, ClubReward} from "./types";
import "./differentials.css";

/* Clube do participante — mobile-first. Nunca exibe números sem ledger ativo. */

export function WalletCard({data}: {data: ClubInsights}) {
  const balance = data.balance;
  return <section className="vfd-wallet" aria-label="Minha carteira de pontos">
    <div className="vfd-wallet-top">
      <span className="vfd-kicker vfd-kicker-on-brand">Clube {data.store.name}</span>
      <Sparkles size={18} aria-hidden="true"/>
    </div>
    {balance ? <>
      <p className="vfd-wallet-label">Disponível para trocar</p>
      <p className="vfd-wallet-balance" aria-live="polite">
        {points(balance.available, true).replace(/ pts?$/, "")}<span> pts</span>
      </p>
      <div className="vfd-wallet-meta">
        <span><Clock3 size={15} aria-hidden="true"/> {points(balance.pending, true)} a liberar</span>
      </div>
    </> : <>
      <p className="vfd-wallet-balance vfd-wallet-balance-soft">Seu clube está sendo preparado</p>
      <p className="vfd-wallet-label">Assim que a loja ativar a pontuação, seu saldo aparece aqui.
        Nenhum número é exibido antes disso.</p>
    </>}
  </section>;
}

export function ExpiryBanner({data}: {data: ClubInsights}) {
  if (!data.expiring) return null;
  const {points: amount, days_left, earliest_expiry} = data.expiring;
  return <aside className="vfd-expiry" role="status">
    <Clock3 size={20} aria-hidden="true"/>
    <div>
      <strong>{points(amount)} vencem {days_left <= 1 ? "hoje" : `em ${days(days_left)}`}</strong>
      <span>A partir de {dateBR(earliest_expiry)}. Use antes dessa data para não perder.</span>
    </div>
    <a className="vfd-link-button" href="#vfd-recompensas">Trocar agora</a>
  </aside>;
}

export function NextGoal({data}: {data: ClubInsights}) {
  const goal = data.goal;
  if (!goal) return null;
  const done = goal.missing_points === 0;
  return <section className="vfd-card vfd-goal" aria-labelledby="vfd-goal-title">
    <div className="vfd-goal-head">
      <span className="vfd-icon-bubble vfd-icon-reward" aria-hidden="true"><Gift size={20}/></span>
      <div>
        <span className="vfd-kicker">{done ? "Pronto para trocar" : "Sua próxima meta"}</span>
        <h2 id="vfd-goal-title">{goal.title}</h2>
      </div>
    </div>
    <div className="vfd-progress" role="progressbar" aria-label={`Progresso até ${goal.title}`}
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={goal.progress_percent}>
      <span style={{width: goal.progress_percent + "%"}}/>
    </div>
    <p className="vfd-goal-message">{goal.message}</p>
  </section>;
}

function rewardBadge(reward: ClubReward) {
  switch (reward.state) {
    case "resgatavel": return <span className="vfd-badge vfd-badge-ok"><Check size={14} aria-hidden="true"/> Você pode trocar</span>;
    case "faltam": return <span className="vfd-badge">Faltam {points(reward.missing_points ?? 0, true)}</span>;
    case "indisponivel": return <span className="vfd-badge vfd-badge-muted">Indisponível</span>;
    default: return <span className="vfd-badge vfd-badge-muted"><LockKeyhole size={13} aria-hidden="true"/> Em preparação</span>;
  }
}

export function RewardShelf({data, onRedeem}: {
  data: ClubInsights; onRedeem?: (reward: ClubReward) => void;
}) {
  const [selected, setSelected] = useState<ClubReward | null>(null);
  return <section className="vfd-section" id="vfd-recompensas" aria-labelledby="vfd-rewards-title">
    <h2 id="vfd-rewards-title" className="vfd-section-title">Recompensas</h2>
    {data.rewards.length === 0
      ? <p className="vfd-empty">A loja ainda não publicou recompensas.</p>
      : <ul className="vfd-rewards">
        {data.rewards.map(reward => <li key={reward.id} className="vfd-reward" data-state={reward.state}>
          <div className="vfd-reward-art" aria-hidden="true"><Gift size={22}/></div>
          <div className="vfd-reward-body">
            <strong>{reward.title}</strong>
            <span className="vfd-reward-cost">{points(reward.points_cost, true)} · vale {brl(reward.perceived_value_cents)}</span>
            {rewardBadge(reward)}
          </div>
          {reward.state === "resgatavel" && onRedeem &&
            <button type="button" className="vfd-button vfd-button-small"
              onClick={() => setSelected(reward)}>Trocar</button>}
        </li>)}
      </ul>}
    {selected && <div className="vfd-sheet-backdrop" onClick={() => setSelected(null)}>
      <div className="vfd-sheet" role="dialog" aria-modal="true" aria-labelledby="vfd-sheet-title"
        onClick={(event: {stopPropagation(): void}) => event.stopPropagation()}
        onKeyDown={(event: {key: string}) => { if (event.key === "Escape") setSelected(null); }}>
        <h3 id="vfd-sheet-title">Trocar {points(selected.points_cost)}?</h3>
        <p>Você recebe <strong>{selected.title}</strong> ({brl(selected.perceived_value_cents)}).
          Os pontos ficam reservados e só são consumidos quando a troca for confirmada.</p>
        <div className="vfd-sheet-actions">
          <button type="button" className="vfd-button vfd-button-ghost" autoFocus
            onClick={() => setSelected(null)}>Cancelar</button>
          <button type="button" className="vfd-button"
            onClick={() => { onRedeem?.(selected); setSelected(null); }}>Confirmar troca</button>
        </div>
      </div>
    </div>}
  </section>;
}

export function RuleExplainer({data}: {data: ClubInsights}) {
  return <section className="vfd-card" aria-labelledby="vfd-rule-title">
    <span className="vfd-kicker"><Info size={14} aria-hidden="true"/> Regras em 30 segundos</span>
    <h2 id="vfd-rule-title">{data.rule.headline}</h2>
    <ol className="vfd-rule-list">
      {data.rule.sentences.slice(1).map(sentence => <li key={sentence}>{sentence}</li>)}
    </ol>
  </section>;
}

export function Milestones({data}: {data: ClubInsights}) {
  if (!data.milestones.length) return null;
  return <section className="vfd-section" aria-labelledby="vfd-milestones-title">
    <h2 id="vfd-milestones-title" className="vfd-section-title">Conquistas</h2>
    {data.milestones.map(item => <article key={item.key} className="vfd-milestone">
      <span className="vfd-icon-bubble vfd-icon-reward" aria-hidden="true"><Award size={20}/></span>
      <div><strong>{item.title}</strong><span>{item.message}</span></div>
    </article>)}
  </section>;
}

export function ShareClub({data}: {data: ClubInsights}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.store.club_url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return <section className="vfd-card vfd-share" aria-labelledby="vfd-share-title">
    <h2 id="vfd-share-title">Convide amigos para o clube</h2>
    <p>Compartilhe o link do clube. Sem promessa de bônus: só um convite.</p>
    <div className="vfd-share-actions">
      <a className="vfd-button vfd-button-whatsapp" target="_blank" rel="noopener noreferrer"
        href={whatsappShareUrl(data.store.name, data.store.club_url)}>Enviar no WhatsApp</a>
      <button type="button" className="vfd-button vfd-button-ghost" onClick={copy}>
        <Link2 size={16} aria-hidden="true"/> {copied ? "Link copiado" : "Copiar link"}</button>
    </div>
  </section>;
}

export function ClubHome({data, onRedeem}: {
  data: ClubInsights; onRedeem?: (reward: ClubReward) => void;
}) {
  return <div className="vfd-club">
    <WalletCard data={data}/>
    <ExpiryBanner data={data}/>
    <NextGoal data={data}/>
    <Milestones data={data}/>
    <RewardShelf data={data} onRedeem={onRedeem}/>
    <RuleExplainer data={data}/>
    <ShareClub data={data}/>
  </div>;
}
