# 46 — Piloto de pontos no balcão (teste controlado)

Decisão do proprietário (18/11/2026): testar pontos de verdade **só no balcão**, **só na loja demo
da Bibelô**, **só em homologação**, sem divulgar a outros lojistas. Flags financeiras globais
continuam `False`; cupom na Nuvemshop continua desligado.

## Portas (todas obrigatórias)
1. `FIDELIZA_ENVIRONMENT=homolog`.
2. ID da loja em `FIDELIZA_PILOT_TENANTS`.
3. Proprietário clica **Ativar piloto** em Configurações → Canais de venda.

Sem custo de produto conferido, o risco fica limitado por **teto por venda** (padrão 1.500 pts =
R$ 15) e **orçamento total** (padrão 50.000 pts = R$ 500). **Pausar agora** congela emissão e uso
de vales na hora, sem apagar nada.

## Fluxo
- **Balcão**: celular → cliente; vale opcional (reserva os pontos); valor; registrar. Quem registrou
  desfaz em até 5 min (vale volta ao saldo).
- **Conferir** (owner/admin): Confirmar → cria lote pendente (`rule_version=pilot-vN`) pela regra de
  Meu clube sobre o valor pago; vale reservado vira usado. Recusar → nenhum ponto; vale volta.
  "Confirmar N sem alerta" ignora vendas com alerta (valor ≥ 10× ticket médio, ou > R$ 2.000 sem
  histórico; fora de 7h–22h; 3+ vendas da mesma cliente em 24 h).
- **Liberação**: depois da carência, o saldo é liberado quando a cliente ou o vendedor consulta.
- **Meu Clube**: mostra saldo real e "Troque no caixa".

## Ativar (operador)
1. Backup do banco. `FIDELIZA_APPLY_MIGRATIONS=1` → Redeploy (cria `sales.0009_counter_pilot`) → volte para `0`.
2. `FIDELIZA_PILOT_TENANTS=<id da loja>` e confirme `FIDELIZA_ENVIRONMENT=homolog` → Redeploy.
3. Meu clube: regra salva e ao menos um vale publicado com uso no balcão.
4. Configurações → Canais de venda → Ativar piloto.

## Desligar
Pausar no painel (imediato) ou esvaziar `FIDELIZA_PILOT_TENANTS` + Redeploy (total).

## Fora do escopo
Pedidos do site não geram pontos; estorno de venda já confirmada não é revertido automaticamente
(recuse antes de confirmar). Status: CÓDIGO VALIDADO só após CI verde; HOMOLOGAÇÃO VALIDADA só
após o fluxo acima executado na loja demo.

## Modo giftback (19/11/2026)
Meu clube → 1. Como ganhar → **Giftback** (um modo por loja; saldos emitidos continuam valendo,
1 ponto = R$ 0,01). Recomendado: 10% de volta, teto R$ 20 por compra, uso em compra ≥ R$ 80,
validade 30 dias, libera em 7 dias. No Balcão o vendedor vê "R$ X de crédito liberado" e aplica o
crédito inteiro (pedido mínimo obrigatório). Confirmar a venda consome o crédito e gera o novo
crédito sobre o valor pago; recusar ou desfazer devolve. Teto por venda e orçamento do piloto
valem igualmente (em centavos). Requer `sales.0010_program_mode`.

## Avisos automáticos (19/11/2026)
Celery Beat roda `sales.pilot_wallet_scan` de hora em hora (minuto 20), só para lojas com piloto
ativo: libera carências vencidas e envia, **uma vez por lote**, "seu crédito/pontos liberou"
(liberações dos últimos 3 dias) e "vence em até 5 dias". Só para quem confirmou o e-mail e marcou
receber novidades (Meu Clube → Perfil); sem isso o aviso fica registrado como não enviado e nunca
dispara depois. Auditoria em `EmailDispatch` tipo `notice`. Requer `core.0007` e `sales.0011` e
o serviço `beat` rodando.
