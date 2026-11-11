import { useEffect, useState, type FormEvent } from "react";
import {
  AlertTriangle, ArrowRight, BadgeCheck, Check, ChevronLeft, ChevronRight,
  ClipboardCheck, Clock3, Database, FileClock, Info, LoaderCircle, LockKeyhole,
  PackageSearch, Pencil, Plus, Search, ShieldAlert, X
} from "lucide-react";
import { ApiError, merchantApi, type CostHistoryEntry, type CostItem, type CostItemInput, type CostList, type CostReviewStatus, type Store } from "./api";
import { brl, parseBrl } from "./finance";

type FormValues = {
  reference: string;
  name: string;
  sku: string;
  external_variant_id: string;
  cost: string;
  price: string;
  provenance: string;
  verify: boolean;
};
const blank: FormValues = {
  reference: "", name: "", sku: "", external_variant_id: "",
  cost: "", price: "", provenance: "", verify: false
};

const stateLabel: Record<CostReviewStatus, string> = {
  missing_cost: "Sem custo",
  needs_review: "A conferir",
  missing_price: "Sem preço",
  ready_for_simulation: "Conferido"
};

const stateDescription: Record<CostReviewStatus, string> = {
  missing_cost: "O custo não foi informado.",
  needs_review: "O custo foi digitado, mas não conferido.",
  missing_price: "Custo conferido; falta preço manual.",
  ready_for_simulation: "Preço e custo foram informados e conferidos pelo lojista."
};

const formFrom = (item: CostItem): FormValues => ({
  reference: item.reference, name: item.name, sku: item.sku,
  external_variant_id: item.external_variant_id,
  cost: item.unit_cost_cents === null ? "" : (item.unit_cost_cents / 100).toFixed(2),
  price: item.selling_price_cents === null ? "" : (item.selling_price_cents / 100).toFixed(2),
  provenance: item.provenance, verify: false
});

function displayCost(value: number | null) {
  return value === null ? "Não informado" : brl(value);
}

export default function CostCatalog({
  tenantId, role, onSimulate
}: { tenantId: string; role: Store["role"]; onSimulate: (item: CostItem) => void }) {
  const canEdit = role === "owner" || role === "admin";
  const [list, setList] = useState<CostList | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [state, setState] = useState<CostReviewStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [editing, setEditing] = useState<CostItem | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [values, setValues] = useState<FormValues>(blank);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [message, setMessage] = useState("");
  const [historyItem, setHistoryItem] = useState<CostItem | null>(null);
  const [history, setHistory] = useState<CostHistoryEntry[] | null>(null);
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setListError("");
    merchantApi.listCosts(tenantId, { q: query, status: state, offset }).then(data => {
      if (active) { setList(data); setLoading(false); }
    }).catch(error => {
      if (active) {
        setListError(error instanceof ApiError ? error.message : "Falha ao carregar os custos.");
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [tenantId, query, state, offset, refresh]);

  const beginNew = () => {
    setEditing(null);
    setValues(blank);
    setFormError("");
    setMessage("");
    setFormOpen(true);
  };

  const beginEdit = (item: CostItem) => {
    setEditing(item);
    setValues(formFrom(item));
    setFormError("");
    setMessage("");
    setFormOpen(true);
  };

  const change = (key: keyof FormValues, value: string | boolean) => {
    setValues(old => ({ ...old, [key]: value }));
    setFormError("");
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canEdit) return;
    setSaving(true); setFormError("");
    try {
      const data: CostItemInput = {
        reference: values.reference.trim(),
        name: values.name.trim(),
        sku: values.sku.trim(),
        external_variant_id: values.external_variant_id.trim(),
        unit_cost_cents: parseBrl(values.cost, true),
        selling_price_cents: parseBrl(values.price, true),
        provenance: values.provenance.trim(),
        verify_cost: values.verify
      };
      if (!data.reference || !data.name) throw new Error("Informe nome e referência do item.");
      if (values.verify && data.unit_cost_cents === null) {
        throw new Error("Informe o custo antes de marcar como conferido.");
      }
      if (values.verify && values.provenance.trim().length < 8) {
        throw new Error("Descreva a origem do custo em pelo menos oito caracteres.");
      }
      if (editing) {
        data.expected_version = editing.version;
        await merchantApi.updateCost(tenantId, editing.id, data);
      } else {
        await merchantApi.createCost(tenantId, data);
      }
      setFormOpen(false);
      setEditing(null);
      setValues(blank);
      setMessage("Item salvo com sucesso. Nenhum produto foi alterado na Nuvemshop.");
      setOffset(0);
      setRefresh(n => n + 1);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Não foi possível salvar. Confira os dados.");
    } finally {
      setSaving(false);
    }
  };

  const showHistory = async (item: CostItem) => {
    setHistoryItem(item); setHistory(null); setHistoryError("");
    try {
      const response = await merchantApi.costHistory(tenantId, item.id);
      setHistory(response.history);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Histórico indisponível.");
    }
  };

  const search = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setOffset(0); setQuery(text.trim());
  };

  return <div className="cost-workspace">
    <section className="cost-hero">
      <div>
        <span className="cost-eyebrow"><ClipboardCheck size={16}/> CATÁLOGO FINANCEIRO <span>•</span> CONTROLE DE MARGEM</span>
        <h2>Conheça seus custos.<br/><em>Recompense com confiança.</em></h2>
        <p>Organize custos por SKU ou variante, registre a origem e descubra quais itens estão prontos para uma simulação de cashback.</p>
        <div className="cost-hero-note"><LockKeyhole size={15}/> Dados internos da loja. Não sincronizados com Nuvemshop ou ERP.</div>
      </div>
      <span className="cost-hero-art" aria-hidden="true"><PackageSearch size={66} strokeWidth={1.4}/></span>
    </section>

    <div className="cost-intro">
      <div><span className="portal-eyebrow">QUALIDADE DO CATÁLOGO</span><h2>Custos e variantes</h2>
        <p>Custo desconhecido nunca é tratado como zero. Preço de venda aqui também é manual.</p>
      </div>
      {canEdit && <button className="portal-primary" onClick={beginNew}><Plus size={18}/> Cadastrar item</button>}
    </div>

    <div className="cost-stats" aria-label="Resumo do catálogo financeiro">
      <div className="cost-stat"><span><Database size={17}/> Itens cadastrados</span><strong>{list?.summary.total ?? "—"}</strong><small>Somente desta loja</small></div>
      <div className="cost-stat"><span><ShieldAlert size={17}/> Sem custo</span><strong>{list?.summary.missing_cost ?? "—"}</strong><small>Precisam de informação</small></div>
      <div className="cost-stat"><span><Clock3 size={17}/> A conferir</span><strong>{list?.summary.needs_review ?? "—"}</strong><small>Custo ainda não validado</small></div>
      <div className="cost-stat"><span><BadgeCheck size={17}/> Conferidos</span><strong>{list?.summary.ready ?? "—"}</strong><small>Aptos para simular</small></div>
    </div>

    <div className="cost-notice"><Info size={19}/><p><b>Comece por um produto.</b> Cadastre o preço e custo que você conhece. Depois confirme a origem. A integração com ERP e Nuvemshop virá após validarmos o mapeamento de variantes.</p></div>

    <section className="cost-panel">
      <div className="cost-panel-header">
        <div><span className="portal-eyebrow">ITENS DA LOJA</span><h3>Catálogo de custos</h3></div>
        {canEdit && <button className="cost-secondary" onClick={beginNew}><Plus size={16}/> Novo item</button>}
      </div>
      <div className="cost-toolbar">
        <form className="cost-search" onSubmit={search}>
          <Search size={18} aria-hidden="true"/>
          <input value={text} onChange={e=>setText(e.target.value)}
            aria-label="Buscar por nome, SKU ou referência" placeholder="Buscar nome, SKU ou referência…" maxLength={80}/>
          <button type="submit">Buscar</button>
        </form>
        <label className="cost-filter"><span>Exibir</span><select aria-label="Filtrar por situação" value={state} onChange={e=>{setOffset(0);setState(e.target.value as CostReviewStatus|"");}}>
          <option value="">Todos os estados</option>
          <option value="missing_cost">Sem custo</option>
          <option value="needs_review">A conferir</option>
          <option value="missing_price">Sem preço</option>
          <option value="ready_for_simulation">Conferidos</option>
        </select></label>
      </div>

      {message && <div className="cost-feedback" role="status"><Check size={17}/>{message}</div>}
      {listError && <div role="alert" className="cost-error">{listError}<button onClick={()=>setRefresh(n=>n+1)}>Tentar novamente</button></div>}

      {loading ? <div className="cost-loading" role="status"><LoaderCircle size={25}/> Carregando itens…</div> :
        !listError && (list?.items.length||0) === 0 ?
          <div className="cost-empty">
            <div className="cost-empty-icon"><PackageSearch size={37}/></div>
            <h3>{list?.summary.total ? "Nenhum item encontrado" : "Seu catálogo começa aqui"}</h3>
            <p>{list?.summary.total ? "Experimente outro termo de busca ou filtro." : "Adicione o primeiro item manualmente. Você poderá controlar custos e registrar quando foram conferidos."}</p>
            {canEdit && <button className="portal-primary" onClick={beginNew}><Plus size={16}/> Cadastrar primeiro item</button>}
          </div> : !listError && <div className="cost-table-scroll">
            <table className="cost-table" aria-label="Itens financeiros cadastrados">
              <thead><tr><th>Produto / referência</th><th>Custo informado</th><th>Preço manual</th><th>Situação</th><th>Ações</th></tr></thead>
              <tbody>{list?.items.map(item => <tr key={item.id}>
                <td><div className="cost-product"><strong>{item.name}</strong><span>Ref.: {item.reference}{item.sku ? " · SKU: "+item.sku : ""}</span>
                  {item.external_variant_id && <small>Variante: {item.external_variant_id}</small>}</div></td>
                <td className="cost-amount">{displayCost(item.unit_cost_cents)}</td>
                <td className="cost-amount">{displayCost(item.selling_price_cents)}</td>
                <td><span className={"cost-status "+item.review_status} title={stateDescription[item.review_status]}>
                  {item.review_status === "ready_for_simulation" ? <BadgeCheck size={15}/> :
                    item.review_status === "missing_cost" ? <ShieldAlert size={15}/> : <Clock3 size={15}/>}
                  {stateLabel[item.review_status]}</span></td>
                <td><div className="cost-actions">
                  {item.review_status === "ready_for_simulation" && <button className="cost-action-primary" onClick={()=>onSimulate(item)}>Simular <ArrowRight size={15}/></button>}
                  {canEdit && <button className="cost-action" onClick={()=>beginEdit(item)} aria-label={"Editar "+item.name}><Pencil size={16}/></button>}
                  <button className="cost-action" onClick={()=>showHistory(item)} aria-label={"Histórico de "+item.name}><FileClock size={16}/></button>
                </div></td>
              </tr>)}</tbody>
            </table>
          </div>}
      {!loading && !listError && list && <div className="cost-pagination"><span>{list.total_filtered} item(ns) no filtro · {list.summary.total} total</span>
        <div><button disabled={offset===0} onClick={()=>setOffset(v=>Math.max(0,v-30))} aria-label="Página anterior"><ChevronLeft size={17}/></button>
          <span>{Math.floor(offset/30)+1}</span>
          <button disabled={offset+30>=list.total_filtered} onClick={()=>setOffset(v=>v+30)} aria-label="Próxima página"><ChevronRight size={17}/></button></div>
      </div>}
    </section>

    {formOpen && <div className="cost-modal-scrim" role="presentation" onClick={e=>{if(e.target===e.currentTarget && !saving)setFormOpen(false);}}>
      <section className="cost-modal" role="dialog" aria-modal="true" aria-labelledby="cost-modal-title">
        <header className="cost-modal-header"><div><span className="portal-eyebrow">DADOS MANUAIS DA LOJA</span><h2 id="cost-modal-title">{editing?"Editar item":"Cadastrar custo por item"}</h2></div>
          <button aria-label="Fechar formulário" disabled={saving} onClick={()=>setFormOpen(false)}><X size={21}/></button></header>
        <p className="cost-modal-hint">A referência identifica o cadastro nesta loja. Nenhum dado será enviado para a Nuvemshop.</p>
        <form onSubmit={save}>
          <div className="cost-form-grid">
            <label className="cost-field wide"><span>Nome do produto *</span><input required maxLength={180} value={values.name} onChange={e=>change("name",e.target.value)} placeholder="Ex.: Argola 100 mm transparente"/></label>
            <label className="cost-field"><span>Referência interna *</span><input required maxLength={100} value={values.reference} onChange={e=>change("reference",e.target.value)} placeholder="Ex.: ARG-100-TR"/></label>
            <label className="cost-field"><span>SKU (opcional)</span><input maxLength={100} value={values.sku} onChange={e=>change("sku",e.target.value)} placeholder="Ex.: 00001001"/></label>
            <label className="cost-field"><span>ID da variante (opcional)</span><input maxLength={64} value={values.external_variant_id} onChange={e=>change("external_variant_id",e.target.value)} placeholder="Identificador confirmado"/></label>
            <label className="cost-field"><span>Preço de venda manual (R$)</span><input inputMode="decimal" value={values.price} onChange={e=>change("price",e.target.value)} placeholder="Ex.: 29,90"/></label>
            <label className="cost-field"><span>Custo unitário manual (R$)</span><input inputMode="decimal" value={values.cost} onChange={e=>change("cost",e.target.value)} placeholder="Deixe vazio se desconhecido"/></label>
            <label className="cost-field wide"><span>Origem da conferência</span><textarea rows={2} maxLength={240} value={values.provenance} onChange={e=>change("provenance",e.target.value)} placeholder="Ex.: custo conferido na nota de compra de teste"/></label>
          </div>
          <label className="cost-verify"><input type="checkbox" checked={values.verify} onChange={e=>change("verify",e.target.checked)}/>
            <span><strong>Conferi o custo informado</strong><small>Requer descrição da origem. Conferência manual não equivale à validação pelo ERP.</small></span></label>
          {editing && <div className="cost-version-note"><Info size={16}/> Versão atual {editing.version}. Alterar o custo remove a conferência anterior até que você o confirme novamente.</div>}
          {formError && <div className="cost-error" role="alert">{formError}</div>}
          <footer className="cost-modal-actions"><button type="button" className="cost-secondary" disabled={saving} onClick={()=>setFormOpen(false)}>Cancelar</button>
            <button className="portal-primary" type="submit" disabled={saving}>{saving?"Salvando…":editing?"Salvar alterações":"Cadastrar item"} <Check size={17}/></button></footer>
        </form>
      </section>
    </div>}

    {historyItem && <div className="cost-modal-scrim" onClick={e=>{if(e.target===e.currentTarget)setHistoryItem(null);}}>
      <section className="cost-modal history" role="dialog" aria-modal="true" aria-labelledby="cost-history-title">
        <header className="cost-modal-header"><div><span className="portal-eyebrow">HISTÓRICO DE ALTERAÇÕES</span><h2 id="cost-history-title">{historyItem.name}</h2></div>
          <button onClick={()=>setHistoryItem(null)} aria-label="Fechar histórico"><X size={21}/></button></header>
        {historyError && <div className="cost-error" role="alert">{historyError}</div>}
        {!history && !historyError && <div className="cost-loading"><LoaderCircle size={22}/> Carregando histórico…</div>}
        {history && <div className="cost-history-list">{history.map((entry,index)=><div className="cost-history-entry" key={entry.version+"-"+index}>
          <div className="cost-history-mark"><FileClock size={17}/></div><div><strong>Versão {entry.version} · {entry.action==="create"?"Cadastro":"Atualização"}</strong>
            <p>{new Date(entry.created_at).toLocaleString("pt-BR")} · {entry.by||"Usuário não disponível"}</p>
            <small>Custo anterior: {entry.before ? displayCost(typeof entry.before.unit_cost_cents==="number"?entry.before.unit_cost_cents:null) : "—"}
              {" → "} atual: {displayCost(typeof entry.after.unit_cost_cents==="number"?entry.after.unit_cost_cents:null)}</small>
          </div></div>)}</div>}
        <div className="cost-modal-actions"><button className="cost-secondary" onClick={()=>setHistoryItem(null)}>Fechar</button></div>
      </section>
    </div>}

    <div className="cost-footer-disclaimer"><AlertTriangle size={17}/> Ainda não importamos custos da Nuvemshop ou do Avanço. Use apenas dados revisados e confira todos os encargos antes de configurar cashback.</div>
  </div>;
}
