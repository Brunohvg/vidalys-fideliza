"""Tarefas do piloto de balcão: varredura horária e e-mail de aviso de saldo.

Sem token, destinatário ou valores em log. O worker confere de novo o consentimento
antes de enviar, porque ele pode ter sido retirado entre a fila e o envio.
"""
import logging
from datetime import datetime

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from apps.core.delivery_tracking import claim_delivery, finish_delivery, retry_or_fail
from apps.core.email_templates import transactional_message
from apps.core.models import EmailDispatch
from apps.participants.email_proof import email_delivery_ready
from apps.participants.models import ProgramParticipant

logger = logging.getLogger(__name__)


@shared_task(name="sales.pilot_wallet_scan", ignore_result=True)
def pilot_wallet_scan():
    from .notices import scan_all
    return scan_all()


@shared_task(name="sales.online_coupon_refresh", queue="nuvemshop", ignore_result=True)
def online_coupon_refresh():
    """Fila isolada com token OAuth: vence cupons, mantém o cupom de giftback em dia e
    devolve à fila os pedidos que o clube não conseguiu processar (tentativas esgotadas)."""
    from apps.nuvemshop.tasks import requeue_club_retries
    from .online import refresh_all
    out = refresh_all()
    requeue_club_retries()
    return out


def _money(cents):
    text = f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + text


def notice_copy(*, store, gift, kind, amount, expires_at, min_order_cents=None):
    """(assunto, título, texto, botão) do aviso — em reais no giftback, em pontos no modo pontos."""
    when = expires_at.strftime("%d/%m")
    value = _money(amount) if gift else f"{amount:,}".replace(",", ".") + " pontos"
    if kind == "released":
        subject = (f"Seu crédito de {value} liberou | {store}" if gift else f"Seus {value} liberaram | {store}")
        title = "Seu crédito está liberado." if gift else "Seus pontos estão liberados."
        text = ((f"Você tem {value} de crédito para usar na próxima compra na {store}"
                 + (f", a partir de {_money(min_order_cents)}" if min_order_cents else "")
                 + f". É só dizer seu celular no caixa. O crédito vale até {when}.") if gift else
                (f"Você tem {value} liberados no clube da {store}. Veja as recompensas e troque no caixa. "
                 f"Os pontos valem até {when}."))
    else:
        subject = (f"Seu crédito de {value} vence em breve | {store}" if gift
                   else f"Seus {value} vencem em breve | {store}")
        title = "Não deixe seu crédito vencer." if gift else "Não deixe seus pontos vencerem."
        text = ((f"Seu crédito de {value} na {store} vence em {when}. Use numa compra antes disso: "
                 "é só dizer seu celular no caixa.") if gift else
                f"Seus {value} na {store} vencem em {when}. Troque por uma recompensa antes disso.")
    return subject, title, text, ("Ver meu crédito" if gift else "Ver meus pontos")


@shared_task(bind=True, max_retries=2, default_retry_delay=120, acks_late=True, ignore_result=True)
def send_credit_notice(self, participant_id: str, kind: str, amount: int, expires_iso: str, event_id=None):
    from .notices import recipient
    from .pilot import pilot_enabled, program_mode
    if not claim_delivery(event_id):
        return "duplicate"
    if not email_delivery_ready():
        finish_delivery(event_id, EmailDispatch.State.SKIPPED, "disabled")
        return "delivery_disabled"
    try:
        participant = ProgramParticipant.objects.select_related("tenant", "local_enrollment").get(pk=participant_id)
    except ProgramParticipant.DoesNotExist:
        finish_delivery(event_id, EmailDispatch.State.SKIPPED, "missing")
        return "not_found"
    try:
        email = recipient(participant)
        if not email or not pilot_enabled(participant.tenant_id) or kind not in ("released", "expiring"):
            finish_delivery(event_id, EmailDispatch.State.SKIPPED, "not_allowed")
            return "skipped"
        tenant = participant.tenant
        gift = program_mode(tenant.pk)
        subject, title, text, label = notice_copy(
            store=tenant.name, gift=bool(gift), kind=kind, amount=int(amount),
            expires_at=timezone.localtime(datetime.fromisoformat(expires_iso)),
            min_order_cents=gift.giftback_min_order_cents if gift else None)
        url = settings.FIDELIZA_PUBLIC_BASE_URL.rstrip("/") + "/clube/" + tenant.slug
        from .online import active_coupon
        coupon = active_coupon(participant)
        if coupon is not None and coupon.state == "issued":
            # Mesmo crédito, dois caminhos: cupom no site ou celular no caixa.
            text += f" No site, use o cupom {coupon.code} (já aplicado pelo botão abaixo)."
            if coupon.apply_url:
                url, label = coupon.apply_url, "Comprar com meu cupom"
        plain, html = transactional_message(
            title=title, greeting="Olá, " + participant.local_enrollment.name + "!",
            description=text, action_label=label, action_url=url,
            context="Clube " + tenant.name,
            safety_note="A loja nunca pede senha ou código por e-mail. O saldo só é usado no caixa ou pelo seu Meu Clube.",
            footer_note=("Você recebe este aviso porque aceitou novidades do clube de " + tenant.name +
                         ". Para parar, desmarque a opção em Meu Clube → Perfil."),
        )
        message = EmailMultiAlternatives(subject=subject, body=plain, from_email=settings.DEFAULT_FROM_EMAIL, to=[email])
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        finish_delivery(event_id, EmailDispatch.State.ACCEPTED)
        return "sent"
    except Exception as exc:
        retry_or_fail(self, event_id, exc)
