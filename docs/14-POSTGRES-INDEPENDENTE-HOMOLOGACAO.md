# Homologacao com PostgreSQL independente

Em 11/11/2026 o usuario autorizou criar variaveis de teste e iniciar o sistema,
considerando o banco fora da stack. Esta preparacao incorpora o planejador da
PR #5 (base e111a2600d019e5248987146e28b7f718e69a27f).

## Topologia aprovada

- Servidor Mexico; projeto vidalys fideliza; ambiente homologacao.
- Destino novo Fideliza Homologacao, rede Docker exclusiva fideliza-homolog.
- PostgreSQL 16 como recurso independente, volume proprio, sem acesso publico.
- Aplicacao Compose no mesmo destino exclusivo, com Connect to predefined network
  habilitado SOMENTE para essa rede nova. Nao conectar ao destino compartilhado coolify.
- Stack da aplicacao: Redis, Django, Celery e frontend, sem banco embutido, sem portas
  publicadas no host e sem volumes de outros produtos.
- Coolify nao troca o destino de um recurso existente: clonar a configuracao para o
  novo destino; preservar a preparacao anterior parada e sem dominio.
- Compose único atual: /compose.yaml, base /, SHA validado.

Separar o banco permite reiniciar/atualizar a aplicacao sem recriar o recurso de
dados e facilita backups proprios no Coolify. Isso nao torna o host dedicado nem
substitui politica de backup e teste de restauracao antes de dados reais.

## Variaveis e acesso

| Variavel | Origem |
| --- | --- |
| DJANGO_SECRET_KEY | Segredo novo e exclusivo, salvo somente no Coolify |
| DATABASE_URL | URL interna real do PostgreSQL novo, mantida oculta |
| DJANGO_ALLOWED_HOSTS | localhost,127.0.0.1 e o hostname HTTPS do staging |
| DJANGO_CSRF_TRUSTED_ORIGINS | Origem HTTPS completa do staging |

O arquivo ativo usa os nomes consumidos pelo Django, sem aliases FIDELIZA_DB_PASSWORD,
FIDELIZA_DJANGO_SECRET_KEY ou SERVICE_PASSWORD_64_DJANGO da preparacao anterior.
Recarregar o Compose e remover essas variaveis obsoletas do recurso novo. Nenhuma senha administrativa e repassada por variavel de ambiente para os containers.\nProvisionar conta piloto apenas por fluxo interativo autorizado e seguro.

Nao imprimir credenciais nem incluir valores em GitHub, capturas ou chat. Nao
copiar senhas, usuarios ou URLs de bancos existentes. Nao criar senha padrao.
O provisionamento de uma conta piloto deve ocorrer por fluxo seguro e somente
para tenant sintetico, sem external_store_id de loja real.

## Protecoes e validacao

DEBUG=0, redirecionamento HTTPS, cookies Secure/HttpOnly da sessao e CSRF ficam
ativos. Nginx limita login por peer a 10 requisicoes/minuto com burst 5. Atras do
proxy isso pode agregar usuarios do staging; e uma guarda conservadora, nao uma
identificacao confiavel do IP individual. O backend tambem limita por conta.
O host emite X-Robots-Tag noindex/nofollow; isso nao e controle de acesso.

O CI utiliza exclusivamente compose.yaml e executa um PostgreSQL separado
no runner, conectando-o temporariamente à rede de teste via Docker CLI.
Não há arquivos Compose de override. A homologação Coolify permanece
na rede privada selecionada e não é alterada pelo CI.

Antes de considerar o deploy aceito: banco e quatro servicos saudaveis no host,
readiness 200, HTTPS valido, ausencia de portas publicas no banco, login/CSRF e
acesso por tenant verificados. Nenhuma integracao Nuvemshop ou beneficio e ativado.

## Referencias verificadas

- https://coolify.io/docs/core/networking/destinations/create
- https://coolify.io/docs/core/networking/destinations/manage
- https://coolify.io/docs/applications/builds/docker-compose
