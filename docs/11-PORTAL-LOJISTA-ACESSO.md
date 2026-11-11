# Portal autenticado do lojista — primeira entrega

**Versão:** piloto, desenvolvido em PR #3, depende de PR #1 e PR #2. Não existe cashback real ou OAuth Nuvemshop. A rota pública /demo é somente demonstração fictícia.

## Benefício para o lojista
Após entrar, o lojista vê somente suas lojas, o tipo de acesso e as próximas etapas. O painel autenticado não mostra vendas, receita, pontos ou recompras fictícias. Em Rentabilidade, digita custos e envia a simulação ao Django autenticado, dentro do tenant selecionado.

## Contrato da sessão e segurança
- GET /api/v1/auth/session/ obtém cookie CSRF e retorna estado da sessão, nome público e lojas vinculadas.
- POST /api/v1/auth/login/ autentica usuário/senha, requer X-CSRFToken, retorna associações; credenciais não persistidas no frontend.
- POST /api/v1/auth/logout/ requer CSRF e encerra a sessão.
- POST /api/v1/tenants/{uuid}/margin-simulations/ requer sessão e associação à loja; NÃO salva cálculo.
- Login limita falhas por usuário no cache compartilhado Redis quando configurado; o staging também exige limitação por IP no proxy, HTTPS e monitoramento de abuso.
- Cookies de sessão HttpOnly, CSRF separado; Secure somente com HTTPS e DJANGO_SECURE_SSL_REDIRECT=1. Fora de TLS configurado, **não disponibilizar login ao público**.
- Nunca guardar cookies, senhas, tokens ou dados pessoais em GitHub, logs ou Notion.

## Criar acesso piloto no ambiente autorizado
1. Suba banco, Redis e API; valide /api/ready/.
2. No container API execute python manage.py createsuperuser com a venv ativa (ou localmente uv run --locked python manage.py createsuperuser).
3. Entre no Django Admin em HTTPS em /admin/ usando sua própria conta administrativa.
4. Em Tenants, crie uma loja de TESTE sem external_store_id real.
5. Associe o usuário desejado ao tenant como owner, admin ou analyst.
6. Acesse /, entre com usuário e senha e confirme acesso apenas à loja vinculada.
7. Para criar um usuário não-admin, use a seção Usuários do Django Admin; nunca reutilize contas reais sem autorização.
8. Se não houver associação, o usuário vê um estado vazio e não consegue simular outra loja.

O cadastro pelo Django Admin é ferramenta provisória de homologação, não a interface comercial. O onboarding OAuth/self-service será desenvolvido depois da validação oficial.

## Verificações
- Login sem CSRF retorna 403.
- Sessão anônima não expõe dados de lojas.
- Usuário A não pode visualizar nem simular tenant B, mesmo sabendo o UUID.
- Login com senha incorreta não informa se usuário existe.
- Logout encerra sessão; nenhuma senha padrão é provisionada.
- Testes Playwright com APIs simuladas verificam login, envio de CSRF e interface 390/768/1440px, mas NÃO substituem testes de integração real do navegador com Django no Coolify.
- A UI em /demo permanece separada da área autenticada.

## Limites e próximos gates
- Painel piloto sem pedidos, faturamento ou cashback real.
- Falta fluxo de convite, recuperação de senha, 2FA, monitoramento de abuso e política de suporte; restringir acesso à homologação.
- Conexão Nuvemshop e descontos reais só com prova de conceito da API vigente.
- O cálculo recebe dados manuais, ainda sem integração com custos Avanço. Custo ausente nunca gera recomendação segura.
