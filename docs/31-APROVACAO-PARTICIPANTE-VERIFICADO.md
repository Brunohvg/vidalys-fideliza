# Continuidade da homologação — cliente verificado, permissões e aprovação

Data: 11/11/2026. Branch de integração: `homolog`. A `main`, a loja
Bibelô e o Coolify **não** foram alterados nesta rodada.

## Mudança 1: permissões reais da Nuvemshop sem bloqueio artificial

O token do app pode conter `read_products`, `read_customers`,
`read_orders` e outros scopes autorizados pelo lojista. O callback
OAuth antes exigia *exatamente* `read_products` ou
`read_products,read_customers`: isso rejeitava instalações legítimas
com mais permissões. Agora a integração valida as capacidades
necessárias e conserva os scopes realmente concedidos no registro
cifrado da instalação, **sem executar novas operações** só porque
o token contém permissões extras.

Quando `write_products` ou `write_customers` estiverem no token,
esses scopes implicam leitura conforme documentação oficial. O
Fideliza implementa apenas métodos GET para consulta de produtos
e clientes nesta fase; nunca invoca escrita da API em nome da loja.

O status separa:
- scope efetivamente concedido pelo token instalado;
- feature flag que permite o produto usar a consulta;
- capacidade disponível de criar participante verificado.

Documentação oficial: https://nuvemshop.dev/docs-api/authentication e
https://nuvemshop.dev/docs-api/resources/unstable/customer

Permissões concedidas no Portal de Parceiros não garantem que a
instalação já tenha o token novo. A documentação exige reautorizar a
loja após mudanças no app. Isso só pode ser comprovado pelo status
da instalação da **própria** loja, não por suposição.

## Mudança 2: aprovação auditável de vínculo de cliente

Após aceitar termos, confirmar o acesso ao e-mail e obter
correspondência única com o Customer oficial, o administrador pode
pressionar **Aprovar participação** (e depois **Sim, aprovar participação**).
A confirmação executa uma nova leitura na Nuvemshop e valida que o
Customer da mesma loja continua com o mesmo e-mail.

Backend:
`POST /api/v1/tenants/{tenant}/enrollment-submissions/{submission}/customer-match/approve/`

Body obrigatório:
`{"customer_id":"351","confirm":true}`

A API exige:
- owner/admin com sessão e CSRF, tenant e loja ativos;
- escopo de clientes concedido na instalação da própria loja;
- e-mail previamente confirmado pelo link e aceite não retirado;
- correspondência exata e não ambígua com o ID informado na prévia;
- feature flags de prévia e aprovação ativas;
- bloqueio temporário de repetição e transação com lock da loja;
- nenhuma adoção automática de um Customer já vinculado por
  uma solicitação anterior.

Na transação são gravados um `ProgramParticipant` e a evidência
`EnrollmentCustomerLink`, associando consentimento, loja, Customer,
hora da aprovação e usuário responsável. Repetir o POST após sucesso
devolve o mesmo participante sem duplicar a base. O vínculo aparece na
lista Participantes e sai da fila de aceites em verificação.

**Não ocorre:** leitura de pedidos, escrita na Nuvemshop, criação de
cashback, disparo promocional, ativação de campanha, resgate ou uso
automático de recompensas.

Retirada confirmada por e-mail depois do vínculo muda o registro de
aceite para `withdrawn`, desativa o opt-in promocional e encerra o
participante no mesmo commit. Guarda-se a trilha de auditoria; não há
apagar silencioso de eventos históricos.

## Gate e implantação

```env
FIDELIZA_PUBLIC_SIGNUP_ENABLED=0
FIDELIZA_EMAIL_DELIVERY_ENABLED=0
FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=0
FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=0
FIDELIZA_LEDGER_WRITES_ENABLED=0
```

Todas as novas funções de efeito real continuam desligadas por
padrão. Não habilitar flags apenas porque os scopes já foram aprovados.

Nova migração: `participants/0005_customer_link_approval` (aplicar
com backup do banco de homologação, jamais no banco compartilhado).

## Qualidade

Testes automáticos Django:
- scopes extras read/write sem desbloquear ações;
- cliente ausente, ambíguo ou ID trocado;
- roles/perfil/tenant e tentativas anônimas;
- idempotência por cliente e por aceitação;
- registro de quem aprovou e versão dos termos;
- retirada após vínculo cancelando participação;
- nenhum lançamento na carteira de cashback;
- recurso desligado por padrão.

Playwright verifica a sequência de consulta e confirmação no painel,
sem termos técnicos expostos ao lojista.

O Compose e o auditor de homologação mantêm
`FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=0` até que o teste
end-to-end no Coolify esteja aprovado.

## Operação não verificada

A sessão de navegador disponível nesta conversa não contém login
registrado no Coolify. O CI pode confirmar o código, mas não
prova qual commit está implantado nem que o banco remoto já recebeu
a migração. Não afirmar implantação, envio SMTP ou consulta real
ao Customer sem evidência.

## Próximas entregas

1. Verificar CI do SHA final em `homolog` e revisar a renderização.
2. Confirmar backup, banco e configuração do app no Coolify.
3. Validar e-mail transacional real de teste e aceite/retirada sem
   cashback, com titular que autorize explicitamente o teste.
4. Tratar webhooks obrigatórios de privacidade Nuvemshop (customer redact,
   store redact, customers data request), retenção e exportação.
5. Só então iniciar `read_orders` com conciliação de pedidos pagos,
   reembolsos, cancelamentos, trilha idempotente e regras de recompensa.

**Decisão de UX:** exibir nomes claros e opções úteis ao lojista; scopes,
SMTP, flags e detalhes de infraestrutura ficam na documentação técnica
ou administração Vidalys, nunca na tela comercial.
