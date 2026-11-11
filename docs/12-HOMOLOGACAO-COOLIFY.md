# Homologacao isolada no Coolify

Inspecao em 11/11/2026. Preparacao de staging; nao equivale a deploy validado.
O escopo nao inclui Nuvemshop, Bibelo, cashback ativo ou producao.

## Inventario observado, sem alterar recursos existentes

| Servidor | Arquitetura / capacidade | Recursos antes desta tarefa | Uso observado no dashboard |
| --- | --- | --- | --- |
| Mexico | aarch64, 2 CPUs, 11,6 GB RAM | 7 | CPU 5%, RAM 20% |
| Vidalys Server | aarch64, 2 CPUs, 11,6 GB RAM | 20 | CPU 21%, RAM 35% |

Os numeros de uso sao uma amostra, nao uma garantia de capacidade. Ambos estao
Ready. O segundo hospeda o proprio Coolify e o Flow em producao. Mexico foi
escolhido para a nova aplicacao; continua sendo um host compartilhado.

Foram encontrados 13 projetos. CRM, Evolution Go, Evolution V2, Jellyfin,
mercado-radar, Merito - V1, n8n, QR-CODE, StockPro, Vidalys Homologacao e Vidalys
Pay usam ambientes chamados production; o Flow (Production) usa flowlog.
O projeto existente vidalys fideliza estava vazio, com somente production.
Criar homologacao nesse projeto evita duplicar projetos e usar production.
Os servicos com falhas preexistentes de CRM/Merito/Pay ficam fora deste escopo.

## Fonte e configuracao

A main ainda e documental. A origem executavel inspecionada foi
feat/merchant-portal-auth-v1, commit a0f8f492f57d938ec4f8faa9a78d1ed3c820262d,
que inclui as fundacoes e o simulador das PRs #1/#2, mais o portal da PR #3.
Esta mudanca de infraestrutura e empilhada sobre essa branch, sem merge em main.

| Campo Coolify | Valor |
| --- | --- |
| Projeto | vidalys fideliza (existente) |
| Ambiente | homologacao |
| Servidor | Mexico |
| Fonte | https://github.com/Brunohvg/vidalys-fideliza |
| Branch | infra/coolify-homologacao-v1 |
| Estrategia | Docker Compose |
| Base directory | / |
| Compose location | /compose.coolify.yaml |
| Automatic deployments / previews | Desabilitados |
| Connect to predefined network | Desabilitado |
| Raw Compose | Desabilitado |
| Domains / portas publicadas | Nenhum nesta preparacao |

O Compose novo usa db, redis, api, worker e frontend. Nao tem nome global,
container_name, portas no host, redes/volumes externos, mounts do host, Docker
socket ou privilegios. Os volumes sao criados no namespace da aplicacao.
Coolify cria a rede especifica do recurso; nao habilitar a rede compartilhada.
Essa e uma separacao logica de containers e dados, nao uma VM dedicada.
Conferir o Compose gerado e as redes efetivas antes de validar o isolamento.

Os limites somam 1536 MiB e 1,35 CPU para runtime. Nao limitam o build; conferir
disco, imagens arm64, memoria livre e ausencia de builds concorrentes antes de
iniciar. Logs rotacionam. O worker so inicia depois da API pronta e migrada.
Nao ha beat ou tarefas de integracao comercial nesta stack.

## Variaveis obrigatorias, somente no recurso novo

| Nome | Preenchimento |
| --- | --- |
| FIDELIZA_DB_PASSWORD | Gerar um segredo exclusivo; nao copiar de outro banco |
| FIDELIZA_DJANGO_SECRET_KEY | Gerar chave exclusiva, forte e estavel |
| FIDELIZA_STAGING_HOST | Host de homologacao sem esquema, porta ou caminho |

Nao preencher valores reais no repositorio, mensagens, screenshots ou logs.
Nesta preparacao os segredos ficam vazios, nao ha senha padrao ou conta demo.
Os operadores :? impedem inicializacao sem configuracao. Nao usar variaveis
compartilhadas de time/projeto nem conexoes de outros produtos.

DEBUG=0 e HTTPS/cookies Secure estao fixos. O readiness local envia o header
de proxy HTTPS para evitar redirecionamento e testa o banco. Somente um futuro
dominio do frontend, porta interna 8080, deve receber trafego externo. O proxy
precisa substituir headers de encaminhamento. Revisar limitacao por IP com
proxies confiaveis antes de disponibilizar login. Nenhum dominio e gerado
automaticamente pelo Compose.

## Gates antes do primeiro deploy de homologacao

1. Revisar o alerta GitGuardian da PR #3 sem divulgar a deteccao. Os quatro jobs
   quality (backend, frontend, docker_smoke, visual_qa) passaram no commit base,
   mas GitGuardian reporta "1 secret uncovered" no historico. Nao presumir falso
   positivo. Se for credencial real, rotacionar no provedor pelo fluxo seguro e
   tratar o historico separadamente, com escopo explicito.
2. Validar o Compose especifico desta branch no CI. Os testes Docker anteriores
   usam compose.yaml local e nao comprovam compose.coolify.yaml no host arm64.
3. Conferir redes/volumes gerados, ausencia de portas no host e de redes externas,
   limites efetivos, disco livre e isolamento em relacao aos recursos existentes.
4. Preencher os dois segredos no Coolify sem valores visiveis ao agente e escolher
   dominio HTTPS de homologacao com acesso restrito. Revisar DNS/certificado e
   limitacao de login; nao alterar proxy global nem dominios de outra aplicacao.
5. Fazer o primeiro deploy manual somente desse recurso, validar migracoes,
   api/health, api/ready, Redis e worker; verificar cookies Secure, CSRF e logout.
6. Provisionar apenas tenant sintetico e conta de teste por fluxo seguro.
   Demonstrar que usuario A nao acessa tenant B, inclusive sabendo o UUID.
7. Testar persistencia por restart e backup/restore em destino novo de teste;
   nenhum restore sobrescreve dados existentes. Registrar capturas sem dados
   pessoais e QA visual em 390/768/1440 px.

## Operacao e reversao

Nao clicar Deploy durante a preparacao. Se o primeiro deploy falhar, parar
somente a nova aplicacao; preservar volumes para diagnostico. Rollback de codigo
nao reverte migracoes: antes de migrações futuras, exigir backup/restore testado.
Nao executar docker prune, down -v, updates do host ou reiniciar o proxy global.
Nao remover ou renomear o ambiente production existente.

## Referencia tecnica verificada

https://coolify.io/docs/applications/builds/docker-compose
(consultada em 11/11/2026: caminhos de build, variaveis obrigatorias, rede por
recurso, portas e healthchecks). O estado renderizado pelo Coolify e a verificacao
em runtime continuam obrigatorios; documentacao nao substitui evidencias.
