"""Tipo de auditoria SMTP para avisos de crédito/pontos liberados ou vencendo."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_member_email_kind")]
    operations = [
        migrations.AlterField(
            model_name="emaildispatch", name="kind",
            field=models.CharField(max_length=10, choices=[
                ("register", "Confirmação de lojista"),
                ("reset", "Redefinição de senha"),
                ("verify", "Confirmação de participante"),
                ("withdraw", "Retirada de participante"),
                ("member", "Acesso ao clube do consumidor"),
                ("notice", "Aviso de saldo do clube"),
            ]),
        ),
    ]
