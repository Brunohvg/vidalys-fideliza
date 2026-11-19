"""Ativa, de uma vez, cadastros com aceite e e-mail CONFIRMADO que ficaram parados em
"aguardando a loja" (lojas Nuvemshop sem ligação ao cliente da Nuvemshop). Sem dados pessoais.

    python manage.py activate_verified_members --tenant <slug>           # só mostra o que faria
    python manage.py activate_verified_members --tenant <slug> --apply   # ativa

Só entra quem aceitou o regulamento e confirmou o e-mail; quem saiu do clube fica de fora.
Mesmo e-mail já ativo na loja: o cadastro passa a apontar para a participação existente.
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from apps.participants.enrollment_models import EnrollmentSubmission
from apps.participants.standalone_activation import activate_verified_submission
from apps.tenants.models import Tenant

LABELS = {"created": "ativadas agora", "joined_existing": "ligadas à participação que já existia",
          "skipped:duplicate_signup": "cadastro repetido (a pessoa já entra pelo anterior)",
          "skipped:existing_needs_review": "mesmo e-mail com participação pausada (decidir na tela de Clientes)",
          "skipped:store_inactive": "loja inativa"}


class Command(BaseCommand):
    help = "Ativa participantes com e-mail confirmado que ficaram aguardando a loja."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError("Loja não encontrada.")
        pending = EnrollmentSubmission.objects.filter(
            tenant=tenant, status=EnrollmentSubmission.Status.EMAIL_VERIFIED,
            email_verified_at__isnull=False, withdrawn_at__isnull=True, participant__isnull=True,
        ).order_by("email_verified_at").values_list("pk", flat=True)
        ids = list(pending)
        self.stdout.write(f"Loja {tenant.slug}: {len(ids)} cadastro(s) confirmado(s) aguardando a loja.")
        if not opts["apply"]:
            self.stdout.write("Nada foi alterado. Rode de novo com --apply para ativar.")
            return
        results = Counter()
        for pk in ids:
            results[activate_verified_submission(pk)] += 1
        for key, count in sorted(results.items()):
            self.stdout.write(f"  {count} {LABELS.get(key, key)}")
