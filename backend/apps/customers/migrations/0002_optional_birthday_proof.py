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
        migrations.AddConstraint(
            model_name="customerprofile",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(birth_date__isnull=True)
                    | models.Q(birth_date_consent_at__isnull=False)
                ),
                name="customer_birth_requires_consent",
            ),
        ),
    ]
