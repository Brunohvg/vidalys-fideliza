# Configurações do lojista — somente funções de uso do cliente

Atualização: 11/11/2026. Implementado diretamente na branch `homolog`.
Solicitação expressa do produto: **não exibir informações de desenvolvedor
na área Configurações nem nos fluxos de adesão do lojista**.

## Diretriz de produto

O painel do lojista e a administração técnica são superfícies diferentes.

**Lojista vê**
- Identidade do clube: nome do programa, cor principal, cor de destaque,
  e-mail para dúvidas e prévia visual.
- Conexão da loja Nuvemshop: conectada/não conectada, botão para
  conectar/atualizar autorização e texto claro sobre disponibilidade.
- Confirmação por e-mail: se está em preparação ou configurada, sem
  marca de fornecedor ou credenciais.
- Regras e adesão: resumo de disponibilidade e atalho para
  editar regulamento/consultar adesões na seção Clientes.
- Página do clube: preparação da página e futura possibilidade
  de endereço próprio, sem URLs fictícias habilitadas.
- Mensagem de segurança: editar a identidade não altera pedidos,
  estoque ou preços da Nuvemshop.

**Lojista NÃO vê**
- SMTP2GO, senha SMTP, nomes de envs, Cloud/Redis/Celery,
  `read_customers`, `read_products`, `OAuth`, tokens,
  IDs de instalações ou de tenants, versões de banco,
  checklists de deploy, TLS/DNS/SSL ou estados de infraestrutura.
- Slugs técnicos e URLs projetadas como se já estivessem publicadas.
- Números de cashback ou métricas fictícias.

Os diagnósticos continuam em scripts de auditoria e documentos
técnicos acessíveis somente à operação Vidalys. O fluxo público do
comprador permanece separado do painel do lojista.

## Persistência e segurança

`GET/PATCH /api/v1/tenants/{tenant_id}/settings/` permite recuperar
ou salvar preferências de aparência. O PATCH recebe a versão
anterior para evitar sobrescritas, gera registro de auditoria, valida
e-mail e cores, e rejeita dados extras/estilos arbitrários.

- OWNER/ADMIN: pode alterar aparência; analista: somente leitura.
- Nome do clube ou programa, cores e contato são por tenant.
- Um conjunto de cores padrão é exibido quando não há personalização.
- A cor principal passa por verificação de contraste com texto branco.
- Uma alteração salva não publica o programa nem muda o checkout.
- A página de adesão pública recebe e aplica a identidade salva
  quando o programa estiver habilitado após os gates de privacidade.
- Banco: migração `tenants/0002_tenant_branding`.
- Nenhuma integração com a loja foi forçada e nenhuma permissão extra
  foi solicitada por este formulário.

## Interface

Nova opção Configurações independente das ferramentas avançadas.
Layout responsivo e coerente com identidade v2 (teal/navy/mint).
A prévia fica ao lado do formulário em desktop e abaixo em mobile.
Avisos são voltados à ação do lojista, sem instruções de deploy.

A opção de **domínio personalizado** permanece planejamento:
não há cadastro DNS ou SSL por essa tela. O sistema nunca exibe
um endereço de adesão ainda não disponível como se estivesse publicado.

## QA

- Django: tenant isolation, role read-only, autorização de edição,
  versão concorrente, auditoria, campos e cores inválidos,
  sem efeitos colaterais em pedidos/clientes.
- Playwright: 390px, 768px e 1440px, conteúdo útil ao lojista,
  ausência dos termos técnicos na tela, edição de nome e bloqueio
  de escrita para analista.
- CI: validar último commit no GitHub antes de considerar homologado.

## Próximos passos

1. Verificar migração e seis grupos de testes em `homolog`.
2. Conferir token OAuth da Nuvemshop já instalado após a autorização
   informada pelo proprietário (portal do app não implica que o token
   instalado recebeu os novos escopos). Apresentar apenas status simples
   ao lojista.
3. Completar o fluxo de adesão verificada e aprovação do vínculo,
   sem crédito automático.
4. Desenvolver gerenciamento de domínio próprio e logo da loja como
   recursos da identidade do programa, com validação segura.
5. Homologar visual e interação no Coolify antes de promover `main`.

**Não alterado:** banco real, loja Bibelô, permissões externas,
deploy Coolify ou a branch `main`.
