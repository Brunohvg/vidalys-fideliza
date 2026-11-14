from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("customers", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="customerprofile", name="birth_date",
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="customerprofile", name="birth_date_consent_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="customerprofile", name="birth_date_verified_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
