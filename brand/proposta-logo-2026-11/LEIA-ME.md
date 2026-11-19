# Proposta de logo — 17/11/2026 (NÃO aplicada no sistema)

Nada nesta pasta é usado pelo site ou pelo painel. É material para decisão.

## Avaliação

| | Prós | Contras |
|---|---|---|
| **Atual** (sacola + estrela + órbita, aprovada em 15/11) | Bonita e reconhecível de 32 px para cima | Gradientes e sombra perdem definição em 16 px; **o texto do logotipo é `<text>` e muda conforme a fonte instalada de quem vê** |
| **Opção A — Sacola-órbita** | Mesmo conceito aprovado, plano, mais limpo em 16–32 px; texto convertido em curvas | Diferença pequena em relação à atual |
| **Opção B — Ciclo** | A mais legível em 16 px; simples | **Lembra o ícone de "atualizar página"**; perde a sacola (varejo) |

**Recomendação:** manter o símbolo atual. Corrigir só o que é técnico:
1. Converter o texto de `brand-logo.svg` e `brand-logo-white.svg` em curvas, com o arquivo da fonte **Manrope** (licença OFL). Aqui eu só tinha a Inter, por isso as opções usam Inter Display.
2. Se quiser um favicon mais nítido em 16 px, usar `opcao-a-favicon.svg` só no favicon, mantendo o símbolo atual no resto.

## Arquivos

- `prancha-logo.png`: comparação em 16/32/48/96 px, na aba do navegador e sobre fundo escuro.
- `opcao-*-simbolo.svg`, `-simbolo-branco.svg`, `-favicon.svg`, `-logo.svg`, `-logo-branco.svg`.
- `gerar_logo.py`: gera tudo de novo (`python gerar_logo.py <pasta>`; requer `fonttools`). Para usar Manrope, troque os nomes dos arquivos de fonte no script.
