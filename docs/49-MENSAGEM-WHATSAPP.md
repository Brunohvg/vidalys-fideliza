# 49 — Mensagem pronta de WhatsApp (página do cliente)

Cartão **Mensagem pronta** na página do cliente (`ClientWhatsApp.tsx`), para qualquer loja.

## Como funciona
- Monta o texto com o saldo real da cliente (`GET .../sales/counter/participants/<id>/wallet/`):
  crédito do giftback (com compra mínima, vencimento mais próximo `next_expiry` e cupom do site),
  vale de pontos que já dá para trocar, ou quanto falta para o próximo vale.
- Tipos: **Avisar crédito/pontos** (quando há saldo), **Campanha** (só com aceite de ofertas e
  campanha no ar) e **Lembrar do clube**. O texto é editável antes de enviar.
- **Abrir no WhatsApp** abre `https://wa.me/?text=<mensagem>` no aparelho do lojista, que escolhe o
  contato. **Copiar** copia o texto.
- Saudação neutra para qualquer nome de loja: "Aqui é da loja <nome>".

## Privacidade e limites
- O Fideliza guarda só HMAC + 4 últimos dígitos do celular, por isso o link não leva o número:
  o cartão mostra "escolha o contato com final 1234".
- Nada é enviado pelo sistema; nenhuma mensagem fica registrada.
- Sem aceite de ofertas: não aparece Campanha e o cartão avisa para usar só como aviso de saldo.
- Participação pausada: o cartão não aparece.
- Próxima fase (decisão de produto): guardar o celular cifrado com consentimento para abrir a
  conversa direto com a cliente, ou integrar a API oficial do WhatsApp Business.
