from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0004_email_dispatch")]

    operations = [
        migrations.AddField(
            model_name="merchantregistration",
            name="cancelled_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="merchantregistration",
            name="blocked_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
