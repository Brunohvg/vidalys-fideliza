# Roteiro do piloto — Vidalys Fideliza

Data: 11/11/2026 (America/Sao_Paulo). Estado: **código em `homolog`, não significa publicação no Coolify**.
Não envolver a loja real nem titulares reais sem autorização específica.

## O que já está validado por testes automáticos

No commit `9a18e36069db2a8f14aad71e2dfda4128708b164`:
- GitHub Actions `43129731279`: seis jobs aprovados (backend,
  frontend, visual_qa, docker_smoke, coolify_compose_smoke,
  external_database_smoke).
- Backend: 175 testes e 78 subtestes passaram; sem novas migrações pendentes.
- Teste integrado:
  `backend/apps/participants/test_complete_homolog_journey.py`.
  Percorre regulamento, adesão pública com CSRF, token de
  confirmação de e-mail, resposta Nuvemshop **simulada**, prévia,
  aprovação, diretório, carteira sem saldo, retirada, replay e
  isolamento entre lojas.
- E-mail não enviado: tarefa de fila capturada por mock. Sem chamada
  à API de clientes real, sem criação de cashback e sem uso de
  dados pessoais verdadeiros.
- Playwright com 320, 360, 390, 430, 768, 1024 e 1440px,
  inclusive foco de menu, ausência de overflow, zoom no Safari
  (verificação de fonte), contraste e estados da loja.
- Foram inspecionadas capturas das telas de configurações em 320
  e 390px; os textos/ações de privacidade não apresentam cortes
  aparentes. Não substituir essa inspeção por prova de Safari real.

## Pré-requisitos para testar a versão publicada

1. Identificar no Coolify o recurso EXATO de homologação, o commit
   publicado, os serviços e o PostgreSQL vinculado.
2. Verificar se o commit publicado é o mesmo aprovado no CI; não
   deduzir isso pela rota `/api/ready/`.
3. Salvar backup **privado e restaurável** do banco de homologação.
   Aplicar migrations somente se a execução e o banco estiverem
   inequivocamente confirmados.
4. Conferir separação de variáveis dos serviços, HTTPS, CSRF,
   Redis/Celery e a ausência de flags de cashback real.
5. Usar **loja de testes** e cadastros sintéticos.
   Não cadastrar a Bibelô real neste roteiro.

## Diagnóstico seguro dentro do container de API

```sh
# Verifica ambiente sem imprimir segredos:
python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br

# Mostra apenas estado interno e contagens da loja de testes:
python scripts/inspect_loyalty_journey.py --slug loja-piloto

# Executa smoke de API transacional e reversível, só no DB homolog
# previamente verificado e com todas as flags externas desativadas:
FIDELIZA_SMOKE_HOMOLOG=1 python scripts/smoke_homolog.py
```

O slug acima é **exemplo**, não uma loja cuja existência foi
confirmada. O script `smoke_homolog.py` bloqueia bancos que não
correspondem ao ambiente seguro esperado. Não alterar a trava nem
executar no banco de produção.

## Jornada manual do lojista — quando o código correto estiver no ar

| Passo | Resultado verificável | Limite |
|---|---|---|
| Entrar e selecionar uma loja | sessão isolada e papel correto | não confundir tela demo com login real |
| Configurações | nome/cor salvos após recarregar e auditoria de versão | não altera loja externa |
| Nuvemshop | OAuth da loja de teste e escopos concedidos | ainda exige autorização no Portal |
| Regras | regulamento com aviso de privacidade separado | não ativa cashback |
| Convite/adesão | cliente sintético registra aceite próprio | habilitar flag só em piloto controlado |
| E-mail | caixa de teste recebe desafio, token de uso único | flag e SMTP reais precisam ser validados |
| Vínculo | prévia consulta cliente exato, confirmação administrativa | exigir escopo e identidade correspondentes |
| Carteira | usuário autorizado visualiza extrato e ausência de benefício real | zero não deve ser inventado |
| Retirada | participante deixa de receber comunicação e não pode ser promovido novamente | saldo/extratos sujeitos a auditoria |
| Privacidade | relatório do titular restrito ao administrador e confirmação explícita | exclusão final ainda exige revisão |
| Campanha | rascunho salvo e simulação de margem visível | não publica nem concede recompensa |
| Pedido pago e cashback | **não disponível** | requer implementação oficial e validação de pagamentos |
| Resgate e estorno reais | **não disponíveis** | dependem de pedidos verificados e motor financeiro |

## Critérios de bloqueio: não ativar a loja real se

- A versão publicada não corresponde ao commit aprovado;
- o banco ou as migrações não foram identificados corretamente;
- não for possível confirmar instalação Nuvemshop, assinatura dos
  webhooks e isolamento de credenciais;
- o SMTP do worker não estiver validado para caixa controlada;
- existirem falhas de CSRF, acesso entre lojas, deduplicação ou
  consentimento;
- o sistema anunciar cashback/resgate como disponível sem pagamento
  confirmado e sem controle de estornos;
- não existir procedimento de retenção/exclusão LGPD com evidência.

## Próxima implementação

**Origem confiável de pagamento**: contrato normalizado de
pedido realmente pago, leitura/verificação de status pela API
oficial da Nuvemshop, reconciliação e proteção contra duplicações.
Só depois disso liberar motor de recompensa pendente, regras de
margem, prazo, estorno e resgate. O adaptador Vidalys Flow fica
como ideia documentada em `docs/36-ADAPTADOR-VIDALYS-FLOW.md`,
**sem implementação nesta etapa**.
