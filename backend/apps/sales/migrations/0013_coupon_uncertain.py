"""Cupom do site com criação incerta: estado "Confirmando" e trilha de auditoria. Só acrescenta."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sales", "0012_online_redemption")]
    operations = [
        migrations.AddField(model_name="onlinecoupon", name="audit", field=models.JSONField(blank=True, default=list)),
        migrations.AlterField(
            model_name="onlinecoupon", name="state",
            field=models.CharField(choices=[("issuing", "Criando"), ("issued", "Disponível"), ("used", "Usado"),
                                            ("cancelled", "Cancelado"), ("expired", "Vencido"), ("failed", "Falhou"),
                                            ("uncertain", "Confirmando")], default="issuing", max_length=10),
        ),
    ]
