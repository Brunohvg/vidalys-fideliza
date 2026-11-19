"""Motor de diferenciais do Vidalys Fideliza (Python puro, sem Django).

Cada módulo responde a uma dor medida no Panorama da Fidelização 2026:

- ``clarity``     — Clube Claro: regra em frases simples e selo de clareza.
- ``expiry``      — Pontos sem Susto: validade renovável e aviso consolidado.
- ``goals``       — Meta com Margem: próxima recompensa priorizando custo baixo.
- ``recognition`` — Reconhecimento sem spam: marcos com limite de frequência.
- ``club_health`` — Prova de retorno honesta: passivo em faixa, taxas com
  intervalo de confiança e grupo de controle de mensagens.

Regras invioláveis deste pacote:
1. Nenhuma função lê/escreve banco, concede pontos ou envia mensagens.
2. Dinheiro sempre em centavos inteiros; pontos sempre inteiros.
3. Custo desconhecido NUNCA vira zero (é ``None`` e sai do cálculo).
4. Sem amostra suficiente, o resultado é "dados insuficientes" — nunca um número.
5. Datas e horas precisam ter fuso (``tzinfo``); datas locais são do tenant.
"""
