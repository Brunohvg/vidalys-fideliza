"""PR26: estado de revogação do cupom Nuvemshop, sem liberar qualquer crédito."""
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0007_pilot_coupons_and_rechecks")]
    operations = [
        migrations.AlterField(
            model_name="nuvemshopcouponintent", name="state",
            field=models.CharField(max_length=24, default="prepared", choices=[
                ("prepared", "Preparado"), ("uncertain", "Resultado HTTP desconhecido"),
                ("issued", "Criado no provedor"),
                ("applied_pending_proof", "Aplicado, captura não comprovada"),
                ("settled", "Baixa financeira validada"),
                ("revoking", "Revogação em processamento"),
                ("revoke_unknown", "Exclusão remota pendente de confirmação"),
                ("revoked", "Cupom confirmado como revogado"),
            ]),
        ),
        migrations.AddField(model_name="nuvemshopcouponintent", name="revoke_reason",
            field=models.CharField(max_length=24, blank=True, default="")),
        migrations.AddField(model_name="nuvemshopcouponintent", name="revoked_at",
            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="nuvemshopcouponintent", name="verified_unused_at",
            field=models.DateTimeField(null=True, blank=True)),
    ]
