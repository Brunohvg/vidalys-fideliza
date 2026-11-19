// Prova que o brand-guard realmente falha (antes, regex com barra dupla nunca disparavam).
// Executar: node --test scripts/brand-guard.test.mjs
import {test} from "node:test";
import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const here = import.meta.dirname;
const TOKENS = ":root{--vf-primary:#6A3DF0;--vf-reward:#FFC857;--vf-purple-900:#3B1E82;--vf-orange:#FF8A3D;--vf-danger:#AD334B}";
const PROTECTED = ["src/MarketingHome.tsx", "src/marketing-home.css", "src/loyalty-dashboard.css",
  "src/ActionCenter.tsx", "public/brand-logo.svg", "public/brand-logo-white.svg",
  "public/brand-mark.svg", "public/favicon.svg"];

function project(overrides = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "brand-guard-"));
  const files = {"src/brand-tokens.css": TOKENS, "src/fideliza-theme.css": ".x{color:var(--vf-primary)}",
    "src/brand-experience.css": ".y{color:var(--vf-ink)}", ...Object.fromEntries(PROTECTED.map(f => [f, ""])),
    ...overrides};
  for (const [rel, content] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), {recursive: true});
    fs.writeFileSync(path.join(root, rel), content);
  }
  fs.mkdirSync(path.join(root, "scripts"));
  fs.copyFileSync(path.join(here, "brand-guard.mjs"), path.join(root, "scripts", "brand-guard.mjs"));
  return spawnSync(process.execPath, [path.join(root, "scripts", "brand-guard.mjs")], {encoding: "utf8"});
}

test("projeto limpo passa", () => {
  assert.equal(project().status, 0);
});

test("tema que redeclara :root falha", () => {
  const run = project({"src/fideliza-theme.css": ":root { --vf-primary: #000 }"});
  assert.equal(run.status, 1);
  assert.match(run.stderr, /redeclares global :root/);
});

test("token obsoleto da marca anterior falha", () => {
  const run = project({"src/Legacy.tsx": "const c = 'var(--vf-mint)';"});
  assert.equal(run.status, 1);
  assert.match(run.stderr, /obsolete brand tokens: --vf-mint/);
});

test("cor legada em arquivo protegido falha", () => {
  const run = project({"src/marketing-home.css": ".a{color:#087f79}"});
  assert.equal(run.status, 1);
});
