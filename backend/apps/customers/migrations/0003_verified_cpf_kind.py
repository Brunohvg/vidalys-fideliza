"""PR26: permitir CPF comprovado por provedor, guardado somente por HMAC."""
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("customers", "0002_optional_birthday_proof")]
    operations = [
        migrations.AlterField(
            model_name="verifiedcustomercontact", name="kind",
            field=models.CharField(max_length=8, choices=[
                ("email", "E-mail"),
                ("phone", "Telefone E.164"),
                ("cpf", "CPF verificado (somente HMAC)"),
            ]),
        ),
    ]
