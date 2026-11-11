import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  AlertTriangle, ArrowRight, BadgeCheck, BookOpen, CheckCheck,
  ClipboardList, FileJson, FileUp, Info, LoaderCircle, LockKeyhole,
  RotateCcw, ScanSearch, SearchCheck, ShieldAlert
} from "lucide-react";
import {
  ApiError, merchantApi, type CatalogDecision, type CatalogPreview
} from "./api";
import { brl } from "./finance";
import NuvemshopConnection from "./NuvemshopConnection";
import type { Store } from "./api";

const example = {
  products: [
    {
      id: 89101, name: { pt: "Fita cetim 10 mm — demonstração" },
      variants: [
        { id: 99301, product_id: 89101, sku: "FITA-10-VERMELHA", barcode: "0780000000123",
          price: "14.90", promotional_price: "12.90", cost: null },
        { id: 99302, product_id: 89101, sku: "FITA-10-AZUL", barcode: "0780000000456",
          price: "14.90", promotional_price: null, cost: "6.50" }
      ]
    },
    {
      id: 89102, name: { pt: "Argola 100 mm — demonstração" },
      variants: [
        { id: 99303, product_id: 89102, sku: "ARG-100-TR", barcode: "",
          price: "29.90", promotional_price: null, cost: null }
      ]
    }
  ]
};

const issueNames: Record<string, string> = {
  duplicate_variant_id: "ID repetido na amostra",
  duplicate_sku_in_sample: "SKU duplicado na amostra",
  ambiguous_local_sku: "SKU encontrado em vários cadastros locais",
  variant_id_changed: "Possível troca de ID da variante",
  confirm_sku_mapping: "Confirmar vínculo pelo SKU",
  sku_changed: "SKU diferente no cadastro local",
  cost_differs_from_local: "Custo divergente",
  price_differs_from_local: "Preço divergente",
  local_cost_not_reviewed: "Custo local ainda não conferido",
};

const resultMeta: Record<CatalogDecision, { name: string; subtitle: string }> = {
  matched: { name: "Correspondente", subtitle: "ID vinculado sem divergências detectadas" },
  review_required: { name: "Revisão necessária", subtitle: "Conferência manual obrigatória" },
  unmapped: { name: "Sem vínculo", subtitle: "Ainda não possui correspondência local" }
};

function formatMoney(value: number | null) {
  return value === null ? "Não informado" : brl(value);
}

function extractPayload(input: string): unknown[] {
  if (!input.trim()) throw new Error("Selecione um arquivo JSON ou cole uma amostra.");
  if (new TextEncoder().encode(input).length > 150000) {
    throw new Error("A amostra não pode superar 150 KB.");
  }
  let raw: unknown;
  try {
    raw = JSON.parse(input);
  } catch {
    throw new Error("O conteúdo não é um JSON válido.");
  }
  const data = Array.isArray(raw) ? raw : (
    raw && typeof raw === "object" && "products" in raw
      ? (raw as { products: unknown }).products
      : null
  );
  if (!Array.isArray(data) || data.length < 1 || data.length > 15) {
    throw new Error("Selecione de 1 a 15 produtos no JSON da amostra.");
  }
  let variantCount = 0;
  return data.map(product => {
    if (!product || typeof product !== "object" || Array.isArray(product)) {
      throw new Error("O JSON contém um produto inválido.");
    }
    const item = product as Record<string, unknown>;
    if (!Array.isArray(item.variants) || item.variants.length < 1) {
      throw new Error("Cada produto precisa incluir variantes.");
    }
    variantCount += item.variants.length;
    if (variantCount > 50) throw new Error("A amostra aceita até 50 variantes.");
    return {
      id: item.id,
      name: item.name,
      variants: item.variants.map(variant => {
        if (!variant || typeof variant !== "object" || Array.isArray(variant)) {
          throw new Error("Uma variante não é um objeto JSON válido.");
        }
        const v = variant as Record<string, unknown>;
        return {
          id: v.id, product_id: v.product_id, sku: v.sku,
          barcode: v.barcode, price: v.price,
          promotional_price: v.promotional_price, cost: v.cost
        };
      })
    };
  });
}

export default function CatalogReconciliation({ tenantId, role }: { tenantId: string; role: Store["role"] }) {
  const [json, setJson] = useState("");
  const [origin, setOrigin] = useState("");
  const [result, setResult] = useState<CatalogPreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<CatalogDecision | "all">("all");
  const requestVersion = useRef(0);

  const clearResult = () => {
    requestVersion.current++;
    setResult(null); setError(""); setBusy(false); setFilter("all");
  };
  const loadExample = () => {
    clearResult();
    setJson(JSON.stringify(example, null, 2));
    setOrigin("Exemplo ilustrativo — não contém produtos reais");
  };
  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    clearResult();
    if (file.size > 150000) {
      setError("Arquivo maior que 150 KB. Selecione uma amostra menor.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".json")) {
      setError("Use um arquivo com extensão .json.");
      return;
    }
    try {
      setJson(await file.text());
      setOrigin("Arquivo local: " + file.name);
    } catch {
      setError("Não foi possível abrir o arquivo. Confira o formato.");
    }
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(""); setResult(null); setBusy(false);
    let products: unknown[];
    try {
      products = extractPayload(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Amostra inválida.");
      return;
    }
    const version = ++requestVersion.current;
    setBusy(true);
    try {
      const data = await merchantApi.reconcileCatalog(tenantId, products);
      if (version === requestVersion.current) setResult(data);
    } catch (e) {
      if (version === requestVersion.current) {
        setError(e instanceof ApiError ? e.message : "Falha de conexão com o servidor.");
      }
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  };

  const items = result?.items.filter(item => filter === "all" || item.decision === filter) ?? [];

  return <div className="reconcile-workspace">
    <section className="reconcile-hero">
      <div>
        <span className="reconcile-kicker"><ScanSearch size={16}/> VARIANTES E CUSTOS <span>•</span> CONCILIAÇÃO</span>
        <h2>Importar sem surpresa.<br/><em>Conferir antes de alterar.</em></h2>
        <p>Compare uma amostra da Nuvemshop com o seu cadastro interno e descubra divergências antes de conectar o catálogo.</p>
        <div className="reconcile-safe"><LockKeyhole size={15}/> Somente análise: nenhuma variante, custo ou pedido será alterado.</div>
      </div>
      <span className="reconcile-art" aria-hidden="true"><ScanSearch size={64} strokeWidth={1.2}/></span>
    </section>

    <NuvemshopConnection tenantId={tenantId} role={role} onLivePreview={live => {
      setResult(live); setError(""); setFilter("all");
      setOrigin("Consulta oficial somente leitura — página " + (live.page || 1));
    }}/>

    <div className="reconcile-steps" aria-label="Etapas da conciliação">
      <span><FileJson size={17}/> 1. Informar amostra</span><ArrowRight size={15}/>
      <span><SearchCheck size={17}/> 2. Comparar IDs e SKUs</span><ArrowRight size={15}/>
      <span><ClipboardList size={17}/> 3. Revisar pendências</span>
    </div>

    <div className="reconcile-grid">
      <section className="reconcile-card reconcile-input-card">
        <div className="reconcile-card-heading"><span className="reconcile-icon"><FileJson size={22}/></span>
          <div><span className="portal-eyebrow">ENTRADA DA AMOSTRA</span>
            <h2>Prévia JSON de produtos</h2><p>Até 15 produtos e 50 variantes. Ainda não acessamos a loja automaticamente.</p></div>
        </div>
        <form onSubmit={submit}>
          <div className="reconcile-upload-actions">
            <label className="reconcile-file-btn"><FileUp size={18}/> Selecionar JSON
              <input type="file" accept=".json,application/json" onChange={onFile} aria-label="Selecionar arquivo JSON"/>
            </label>
            <button type="button" className="reconcile-example-btn" onClick={loadExample}><BookOpen size={18}/> Usar exemplo fictício</button>
          </div>
          {origin && <div className="reconcile-origin"><Info size={16}/>{origin}</div>}
          <label className="reconcile-input-label" htmlFor="reconcile-json">Ou cole o JSON de uma amostra autorizada</label>
          <textarea id="reconcile-json" value={json} rows={12}
            placeholder={'{"products":[{"id":123,"name":{"pt":"Produto"},"variants":[{"id":456,"sku":"SKU-1","barcode":"078...","price":"19.90","cost":null}]}]}'}
            onChange={e=>{clearResult();setJson(e.target.value);setOrigin("Amostra colada manualmente");}}
            spellCheck={false} aria-describedby="reconcile-security"/>
          <div className="reconcile-input-foot" id="reconcile-security">
            <ShieldAlert size={16}/>
            <span>Não cole tokens, dados de clientes ou segredos. A prévia envia apenas IDs, nomes e campos de variantes selecionados.</span>
          </div>
          {error && <div className="reconcile-error" role="alert"><AlertTriangle size={17}/>{error}</div>}
          <div className="reconcile-action-row">
            <button type="button" className="reconcile-reset" onClick={() => {clearResult();setJson("");setOrigin("");}}><RotateCcw size={16}/> Limpar</button>
            <button className="portal-primary" type="submit" disabled={busy || !json.trim()}>
              {busy ? <><LoaderCircle size={17} className="reconcile-spin"/> Comparando…</> :
                <><SearchCheck size={17}/> Analisar variantes</>}
            </button>
          </div>
        </form>
      </section>
      <section className="reconcile-card reconcile-result-card" aria-live="polite">
        <div className="reconcile-card-heading"><span className="reconcile-icon aqua"><ClipboardList size={22}/></span>
          <div><span className="portal-eyebrow">DIAGNÓSTICO</span>
            <h2>Resultado da prévia</h2><p>Somente os registros da loja selecionada serão comparados.</p></div>
        </div>
        {!result ? <div className="reconcile-empty"><ScanSearch size={43}/>
          <h3>{busy ? "Conferindo a amostra…" : "Pronto para comparar"}</h3>
          <p>Carregue um JSON ou utilize o exemplo fictício para conhecer os alertas de importação.</p>
        </div> : <>
          <div className="reconcile-complete"><CheckCheck size={20}/><div><b>Análise concluída, nenhuma alteração realizada.</b><span>{result.source==="nuvemshop_live_read_only"?"Amostra consultada via API oficial; nenhum dado foi alterado.":"Amostra fornecida manualmente; não representa consulta ao vivo."}</span></div></div>
          <div className="reconcile-stats">
            <div><span>Variantes analisadas</span><strong>{result.summary.variants}</strong></div>
            <div><span>Correspondentes</span><strong>{result.summary.matched}</strong></div>
            <div><span>Revisar</span><strong>{result.summary.review_required}</strong></div>
            <div><span>Sem vínculo</span><strong>{result.summary.unmapped}</strong></div>
          </div>
          <div className="reconcile-caution"><Info size={18}/><span>
            <b>{result.summary.missing_api_cost} variante(s) sem custo na amostra.</b> Ausência não equivale a custo zero. O cadastro interno permanece intacto.
          </span></div>
          <div className="reconcile-mini-chart">
            <span>Qualidade do mapeamento nesta amostra</span>
            <div className="reconcile-bar" aria-label="Proporção dos resultados">
              <i style={{width:(result.summary.variants ? result.summary.matched/result.summary.variants*100 : 0)+"%"}} className="ok"/>
              <i style={{width:(result.summary.variants ? result.summary.review_required/result.summary.variants*100 : 0)+"%"}} className="review"/>
              <i style={{width:(result.summary.variants ? result.summary.unmapped/result.summary.variants*100 : 0)+"%"}} className="unknown"/>
            </div>
            <small>Apenas uma amostra. Não é a cobertura completa do catálogo da loja.</small>
          </div>
        </>}
      </section>
    </div>

    {result && <section className="reconcile-card reconcile-table-card">
      <div className="reconcile-table-heading"><div><span className="portal-eyebrow">RESULTADOS POR VARIANTE</span><h2>Pendências e correspondências</h2></div>
        <div className="reconcile-tabs" aria-label="Filtrar resultado">
          {([
            ["all", "Todos"],["review_required", "Revisar"],
            ["unmapped", "Sem vínculo"],["matched", "Correspondentes"]
          ] as const).map(([key,label]) => <button key={key} type="button"
            aria-pressed={filter===key} onClick={()=>setFilter(key)}
            className={filter===key?"is-active":""}>{label}</button>)}
        </div>
      </div>
      {items.length===0 ? <div className="reconcile-empty compact">Nenhuma variante nesse filtro.</div> :
      <div className="reconcile-table-wrap">
        <table className="reconcile-table">
          <thead><tr><th>Produto e variante</th><th>Preço Nuvemshop</th><th>Custo na amostra</th><th>Custo local</th><th>Diagnóstico</th></tr></thead>
          <tbody>{items.map((item,index)=><tr key={item.product_id+":"+item.variant_id+":"+index}>
            <td><strong>{item.product_name}</strong>
              <small>Variante: {item.variant_id} · SKU: {item.sku || "Sem SKU"}</small>
              {item.barcode && <small>EAN/GTIN: {item.barcode}</small>}</td>
            <td>{formatMoney(item.price_cents)}{item.promotional_price_cents!==null &&
              <small>Promoção: {formatMoney(item.promotional_price_cents)}</small>}</td>
            <td>{formatMoney(item.api_cost_cents)}</td>
            <td>{formatMoney(item.local_cost_cents)}{item.local_reference && <small>Ref.: {item.local_reference}</small>}</td>
            <td><span className={"reconcile-status "+item.decision}>
              {item.decision==="matched"?<BadgeCheck size={15}/>:<AlertTriangle size={15}/>}
              {resultMeta[item.decision].name}</span>
              {item.issues.length>0 && <ul>{item.issues.map(issue=><li key={issue}>{issueNames[issue]||issue}</li>)}</ul>}
              {item.issues.length===0 && <small>{resultMeta[item.decision].subtitle}</small>}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      <div className="reconcile-readonly"><LockKeyhole size={16}/> Apenas leitura. Nenhum custo foi sobrescrito; nenhum ID de variante foi vinculado automaticamente.</div>
    </section>}
    <div className="reconcile-footer"><Info size={18}/> A conexão OAuth, a busca automática e uma importação real exigirão validação das permissões e conferência de uma amostra representativa. Nesta etapa só analisamos o JSON enviado.</div>
  </div>;
}
