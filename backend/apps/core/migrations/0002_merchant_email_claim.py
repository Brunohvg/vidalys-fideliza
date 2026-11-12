"""Reivindicação única de caixa postal, com backfill não destrutivo."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def canonical(address):
    email = address.strip().casefold()
    if "@" not in email:
        return email
    local, domain = email.rsplit("@", 1)
    if domain in ("gmail.com", "googlemail.com"):
        return local.split("+", 1)[0].replace(".", "") + "@gmail.com"
    return email


def backfill_claims(apps, schema_editor):
    Claim = apps.get_model("core", "MerchantEmailClaim")
    Identity = apps.get_model("core", "MerchantEmailIdentity")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    # Reservar primeiro os emails confirmados, depois contas legadas.
    # Duplicidade histórica preexistente não é apagada nem resolvida por acaso;
    # novos cadastros ficam bloqueados pelo cheque de emails legados.
    reserved = set()
    for row in Identity.objects.order_by("pk").values("user_id", "normalized_email"):
        key = canonical(row["normalized_email"])
        if not key or key in reserved:
            continue
        if not Claim.objects.filter(user_id=row["user_id"]).exists():
            Claim.objects.create(user_id=row["user_id"], canonical_email=key)
        reserved.add(key)
    for user in User.objects.order_by("pk").values("pk", "email"):
        if not user["email"] or "@" not in user["email"]:
            continue
        key = canonical(user["email"])
        if not key or key in reserved:
            continue
        if not Claim.objects.filter(user_id=user["pk"]).exists():
            Claim.objects.create(user_id=user["pk"], canonical_email=key)
        reserved.add(key)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_merchant_auth"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="MerchantEmailClaim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                             serialize=False, verbose_name="ID")),
                ("canonical_email", models.EmailField(max_length=254, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                   related_name="merchant_email_claim", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(backfill_claims, migrations.RunPython.noop),
    ]
