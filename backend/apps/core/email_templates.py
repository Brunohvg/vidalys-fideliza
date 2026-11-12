"""E-mails transacionais Vidalys: HTML responsivo + alternativa plain text.

Compatível com Gmail, Outlook e clientes sem imagens. Sem CSS remoto, tracking,
credenciais ou dados de terceiros. Logo estático público do próprio projeto.
"""
from html import escape

from django.conf import settings


def transactional_message(*, title, greeting, description, action_label, action_url,
                          context, safety_note, footer_note):
    """Retorna (plain, HTML). Toda entrada dinâmica é escapada no HTML."""
    base = settings.FIDELIZA_PUBLIC_BASE_URL.rstrip("/")
    logo_url = base + "/email-assets/vidalys-fideliza-logo.png"
    text = (
        f"VIDALYS FIDELIZA\n\n{title}\n\n{greeting}\n\n{description}\n\n"
        f"{action_label}:\n{action_url}\n\n"
        f"{context}\n\n{safety_note}\n\n"
        f"{footer_note}\n\n"
        "Este é um e-mail automático. Se precisar de ajuda, abra o portal Vidalys Fideliza."
    )
    esc = lambda value: escape(str(value), quote=True)
    # Tabelas + estilos inline: degradam com legibilidade ao bloquear imagens.
    html = f"""<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>
@media screen and (max-width:640px){{
  .email-outer{{padding:14px!important}}
  .email-content{{padding:28px 22px!important}}
  .email-title{{font-size:27px!important;line-height:1.22!important}}
  .email-button{{display:block!important;text-align:center!important}}
}}
</style></head>
<body style="margin:0;padding:0;background-color:#f3f7f7;color:#10253e;font-family:Arial,Helvetica,sans-serif;">
<div style="display:none;font-size:1px;color:#f3f7f7;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">
{esc(description[:120])}</div>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f3f7f7;border-collapse:collapse;">
<tr><td align="center" class="email-outer" style="padding:34px 16px 42px">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:600px;border-collapse:separate;border-spacing:0;">
<tr><td style="padding:24px 28px;background:#ffffff;border:1px solid #e0ebe8;border-radius:16px 16px 0 0;">
  <img src="{esc(logo_url)}" alt="Vidalys Fideliza" width="216" height="40"
       style="display:block;max-width:216px;width:100%;height:auto;border:0;text-align:left;color:#10253e;font-size:20px;font-weight:bold;">
</td></tr>
<tr><td class="email-content" style="background:#ffffff;padding:38px 42px 34px;border-left:1px solid #e0ebe8;border-right:1px solid #e0ebe8;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
  <tr><td style="padding:0 0 14px;">
    <span style="font-size:11px;letter-spacing:1.8px;font-weight:bold;color:#087f79;text-transform:uppercase;">{esc(context)}</span>
  </td></tr>
  <tr><td><h1 class="email-title" style="margin:0 0 24px;font-size:32px;line-height:1.19;letter-spacing:-0.6px;font-weight:700;color:#10253e;">{esc(title)}</h1></td></tr>
  <tr><td><p style="margin:0 0 12px;color:#233e55;font-size:16px;line-height:1.65;">{esc(greeting)}</p>
  <p style="margin:0 0 28px;color:#425a6a;font-size:15px;line-height:1.75;">{esc(description)}</p></td></tr>
  <tr><td style="padding:0 0 24px;">
    <a class="email-button" href="{esc(action_url)}" role="button" style="display:inline-block;padding:17px 27px;border-radius:11px;background:#087f79;color:#ffffff;text-decoration:none;font-size:15px;line-height:1.2;font-weight:700;">{esc(action_label)}</a>
  </td></tr>
  <tr><td style="background:#e8f9f4;border-left:3px solid #37d5bb;border-radius:7px;padding:16px 17px;">
    <p style="margin:0;font-size:13px;line-height:1.6;color:#254b47;">{esc(safety_note)}</p>
  </td></tr>
  </table>
</td></tr>
<tr><td style="background:#f9fbfa;padding:22px 28px;border:1px solid #e0ebe8;border-top:0;border-radius:0 0 16px 16px;">
  <p style="margin:0 0 8px;color:#526c73;font-size:12px;line-height:1.7;">{esc(footer_note)}</p>
  <p style="margin:0;color:#78908d;font-size:11px;line-height:1.6;">Mensagem automática de segurança · Vidalys Fideliza · Não responda a este e-mail.</p>
</td></tr>
</table>
</td></tr></table></body></html>"""
    return text, html
