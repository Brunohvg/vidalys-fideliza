"""Persist source of truth for verified voucher redemption."""
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("loyalty", "0002_voucher_reward_origin")]
    operations = [
        migrations.AddField(
            model_name="loyaltyvoucher", name="redemption_sale",
            field=models.OneToOneField(
                to="sales.salerecord", related_name="redeemed_loyalty_voucher",
                on_delete=django.db.models.deletion.PROTECT, null=True, blank=True,
            ),
        ),
        migrations.AddField(
            model_name="loyaltyvoucher", name="redemption_evidence",
            field=models.OneToOneField(
                to="loyalty.financialevidence", related_name="redeemed_loyalty_voucher",
                on_delete=django.db.models.deletion.PROTECT, null=True, blank=True,
            ),
        ),
    ]
