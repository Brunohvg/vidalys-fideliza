/* Service worker do app do clube. Não guarda dados do cliente nem respostas
   da API: só mostra uma tela amigável quando o celular está sem internet. */
const OFFLINE = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sem conexão</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#F8F9FF;color:#24113F;
font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px}button{margin-top:16px;min-height:48px;padding:0 24px;
border:0;border-radius:999px;background:#3B1E82;color:#fff;font:700 16px system-ui}</style></head>
<body><main><h1>Você está sem internet</h1><p>Seu clube volta assim que a conexão voltar.</p>
<button onclick="location.reload()">Tentar de novo</button></main></body></html>`;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", event => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(fetch(event.request).catch(() =>
    new Response(OFFLINE, {headers: {"Content-Type": "text/html; charset=utf-8"}})));
});
