# Autenticação real no CI — gate adicional antes do Coolify

Esta branch não implanta nada no servidor. Acrescenta um teste **Django + PostgreSQL externo + Nginx**, com requisições HTTP reais na rede privada do runner e com a origem HTTPS simulada pelo proxy.

## O que foi melhorado

- A variável opcional FIDELIZA_TEST_ADMIN_PASSWORD foi retirada do Compose. Não havia criação automática de administrador e não existe motivo para distribuir uma senha adicional aos containers de API e worker.
- O novo teste tem guarda dupla: só executa com FIDELIZA_CI_ISOLATED=1 e exige o banco descartável do CI (nome fideliza, host fideliza-db, engine PostgreSQL).
- Usuário e duas lojas artificiais são criados com dados e senha aleatórios somente em banco descartável, removidos após o teste.
- O teste passa pela camada real Nginx -> Django e verifica o cookie CSRF Secure, login sem CSRF rejeitado, login válido, cookie de sessão Secure/HttpOnly, sessão autenticada, associação a uma única loja, API de margem, API de orçamento, proteção contra acesso a tenant alheio, logout e acesso revogado.
- Nenhum segredo/senha é escrito em log, repositório ou Notion. O teste não usa APIs Nuvemshop nem dados reais da Bibelô.

## Limites

- O teste executa HTTP entre containers e informa X-Forwarded-Proto: https para simular TLS terminado no Coolify Proxy. Isso valida a configuração Django/Nginx, mas **não prova** que há certificado HTTPS válido nem roteamento externo correto no servidor real.
- O teste também não prova backup/restore, arquitetura ARM64, rede exclusiva, portas privadas reais, limitação por IP, disponibilidade de disco ou a integração de Nuvemshop. Verificar esses fatores presencialmente no Coolify Work.
- O limite Nginx por peer pode agrupar usuários atrás do proxy; deve haver verificação específica do tráfego real e ajuste conforme política de acesso restrito.
- O alerta histórico do GitGuardian no PR #3 continua exigindo classificação no painel, independentemente de novos CI verdes.

## Checklist de aceite real no Coolify

1. Confirmar a branch/commit e o Compose efetivamente publicados em homologação.
2. Confirmar rede de destino exclusiva, banco separado, URL **interna** e nenhuma porta pública de PostgreSQL/Redis.
3. Confirmar DNS, certificado HTTPS, Host, CSRF e cookies Secure/HttpOnly em navegador real.
4. Criar apenas contas e lojas sintéticas, sem reutilizar credenciais de outros projetos.
5. Repetir login/logout, acesso a tenant autorizado e tentativa a outro tenant, margem e orçamento por API.
6. Confirmar backups do banco e restauração em recurso descartável, sem tocar dados existentes.
7. Verificar consumo e limites do servidor arm64, logs sem segredos e plano de reversão.
8. Documentar falhas e bloquear publicação até todos os critérios acima serem atendidos.

Status: esta etapa é um gate de integração para homologação, não uma funcionalidade comercial de cashback.
