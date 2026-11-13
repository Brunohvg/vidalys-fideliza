"""Tipo adicional de auditoria SMTP para acesso ao Clube do Cliente."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0005_registration_moderation")]
    operations = [
        migrations.AlterField(
            model_name="emaildispatch", name="kind",
            field=models.CharField(max_length=10, choices=[
                ("register", "Confirmação de lojista"),
                ("reset", "Redefinição de senha"),
                ("verify", "Confirmação de participante"),
                ("withdraw", "Retirada de participante"),
                ("member", "Acesso ao clube do consumidor"),
            ]),
        ),
    ]
