from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0002_merchant_email_claim")]
    operations = [
        migrations.AlterModelOptions(
            name="merchantregistration",
            options={
                "verbose_name": "Cadastro de lojista",
                "verbose_name_plural": "Cadastros de lojistas",
            },
        ),
    ]
