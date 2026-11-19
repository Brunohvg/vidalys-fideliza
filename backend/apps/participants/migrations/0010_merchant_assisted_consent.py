"""Cadastro feito pela loja (com autorização declarada da cliente). Só acrescenta uma opção."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("participants", "0009_member_birthday")]
    operations = [
        migrations.AlterField(
            model_name="programparticipant", name="consent_channel",
            field=models.CharField(choices=[("customer_portal", "Portal do participante"),
                                            ("storefront_opt_in", "Aceite na vitrine"),
                                            ("merchant_assisted", "Cadastro pela loja com autorização da cliente")],
                                   max_length=32),
        ),
    ]
