"""PR28: persist verified-unused remote snapshot before potentially uncertain DELETE."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0009_immutable_revocation_audit")]
    operations = [
        migrations.AddField(
            model_name="nuvemshopcouponintent",
            name="verified_unused_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
