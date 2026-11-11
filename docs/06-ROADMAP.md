# Roadmap e gates do projeto

## Fase 0 — Descoberta (gate obrigatório)
- [ ] 5–10 entrevistas de lojistas; concorrência e preço aceito.
- [ ] Validar nome no INPI/domínios e marca.
- [ ] Confirmar margens/custo de incentivos com Avanço/contabilidade.
- [ ] Aplicativo privado Nuvemshop com OAuth e permissions/scopes reais.
- [ ] POC: cliente identificado, desconto parcial, resgate, webhook, expirou, Pix, cupom, frete grátis, checkout.
- [ ] Parecer fiscal/jurídico do crédito promocional, validade e LGPD.

## Fase 0.5 — Direção visual (gate obrigatório P0)
- [ ] Mapear fluxos e telas de lojista, comprador e operador SaaS.
- [ ] Criar wireframes e protótipos de alta fidelidade para dashboard, regras e carteira mobile.
- [ ] Definir e validar o design system e logotipo com a família Vidalys.
- [ ] QA visual e responsivo em 390, 768 e 1440 px, estados de UI e acessibilidade AA.
- [ ] Não tratar Django Admin ou templates genéricos como UI comercial entregue.

## Fase 1 — Fundamentos
- [ ] Criar repo `vidalys-fideliza` separado de Flow.
- [ ] Docker + Django/DRF + Postgres + Redis/Celery + .env.example sem tokens reais.
- [ ] Tenant, RBAC, health, migrations, testes, observabilidade, CI.

## Fase 2 — Motor financeiro
- [ ] Ledger, reservas e idempotência; regras versionadas; cashback e pontos.
- [ ] Expiração, estorno, reconciliação e teste de concorrência.

## Fase 3 — App e interface
- [ ] Configuração lojista, carteira autenticada, Nuvemshop callback real, widget não invasivo.
- [ ] QA checkout no Ipanema e outras lojas.

## Fase 4 — Piloto
- [ ] Ativar somente após aprovação; orçamento de incentivo, contingência e suporte.
- [ ] 60–90 dias com grupo controle viável e medição de recompra e margem.

## Fase 5 — Plataforma comercial
- [ ] Billing, planos e limites, homologação pública, suporte, monitoramento, documentação, termos.

## Critérios de aceite principais
- Evento duplicado não duplica pontos; duas reservas paralelas nunca duplicam gasto.
- Sem checkout pago, não debitar benefício; pedido cancelado exige contralançamento.
- Tenants não vazam dados; cliente anônimo não lê saldo.
- Sem custo de produto cadastrado, margem é desconhecida, nunca zero.
- Sem endpoint oficial validado, POC não é concluída.
- Credenciais e dados pessoais não aparecem em logs do navegador.
