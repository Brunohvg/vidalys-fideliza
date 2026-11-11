# Cadastro público por loja — pré-adesão validada, sem cashback ativo

Registro: 11/11/2026. Desenvolvimento na `homolog`, preservando apenas
`main` e `homolog` no repositório.

## Experiência do comprador

Cada loja aprovada poderá divulgar sua URL própria:
`https://HOST_DA_HOMOLOGACAO/participar/<slug-da-loja>`.

A página mostra marca/nome da loja, versão do regulamento, regras completas e
aviso de privacidade **em seção separada**. Solicita nome e e-mail,
confirmação obrigatória dos termos e opt-in opcional de marketing
(desmarcado por padrão). O comprador pode desistir sem se cadastrar.
A página mantém o design responsivo v2.

Ao enviar, o servidor registra uma **solicitação de adesão** com versão,
digest do texto de regras + aviso de privacidade, horário, nome/e-mail
informados e escolha independente de marketing. Responde
`pending_verification`: **não cria participante ativo**, não confirma
email, não libera saldo, recompensa, programa nem mensagem promocional.

## Pré-requisitos para disponibilizar a página pública

- `Tenant.status == active`; a loja suspensa/rascunho não expõe formulário.
- Termos criados e aprovados por proprietário/admin em `Clientes`.
- `privacy_notice` aprovado e preenchido com 120 a 2.500 caracteres.
- Um único regulamento ativo por loja; versão antiga fica arquivada e
  página pública exibe apenas o regulamento vigente.
- Os documentos legais reais são responsabilidade da loja e exigem revisão
  sobre finalidade/base legal, identidade do controlador, prazo de
  retenção, acesso, correção, retirada da adesão e comunicação.

## Endpoints

- `GET /api/v1/public/programs/{slug}/`: dados públicos do programa,
  regulamento e aviso de privacidade, sem lista de clientes.
- `POST /api/v1/public/programs/{slug}/join/`: registro de aceite,
  exigir CSRF e versão vigente.
- `POST /api/v1/public/enrollment/preview/` e
  `POST /api/v1/public/enrollment/accept/`: fluxo alternativo
  de convite individual de uso único, com validade de 24 horas.

O servidor bloqueia payloads com campos não previstos, dá 409 para versão
desatualizada, 404 para loja inativa/não configurada e 429 quando
ultrapassados limites de inscrições. Limite inicial: 40 novas solicitações
por loja em 24h; duplicatas pelo mesmo e-mail na fila não criam novo
registro e recebem resposta neutra.

## Distinções essenciais

| Registro | O que confirma | O que NÃO confirma |
| --- | --- | --- |
| Solicitação pública | O formulário foi enviado com aceite e versão | Titularidade do e-mail e identidade do comprador |
| Convite individual | Um token válido foi consumido com aceite | Identidade do cliente da Nuvemshop |
| ProgramParticipant | Futuro vínculo confirmado com identidade da loja | Cashback liberado automaticamente |
| CashbackWallet | Futuro ledger interno auditável | Direito de resgate sem integração oficial |

## Pendências para piloto com dados pessoais reais

1. Revisar juridicamente aviso e regulamento por loja; publicar política de
   privacidade adequada e canais de contato.
2. Implementar confirmação de propriedade do e-mail/conta e vínculo
   idempotente com o identificador oficial do cliente Nuvemshop.
3. Implementar solicitação de retirada e exclusão/retenção no fluxo do
   cliente, além de exportação de evidências quando necessário.
4. Adicionar proteção anti-bot proporcional e limites adequados à escala.
5. Verificar regras para menores de idade conforme público e dados tratados.
6. Testar fluxo com dados sintéticos em 390/768/1440px e conferir
   isolamento por tenant e limites no PostgreSQL.
7. Sem publicação automática no tema Ipanema, checkout, Bibelô ou Coolify.
   `main` permanece inalterada.

## QA

- Django: aprovação de documentos, loja ativa, duplicatas, termos antigos,
  payloads, CSRF anônimo e ausência de carteira/participante.
- Playwright: formulário e aviso de privacidade em 390px, 768px e 1440px.
- Migração `participants/0003_privacy_notice`; após backup se for
  atualizar a homologação real.

**Nota:** Cadastro público é uma pré-adesão. Um contrato apresentado e
marcado no formulário não substitui, por si só, prova de titularidade do
contato ou adequação jurídica à LGPD.
