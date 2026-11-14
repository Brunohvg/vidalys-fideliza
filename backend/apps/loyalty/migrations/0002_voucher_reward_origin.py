"""Vouchers vinculados à recompensa comercial e às origens de cashback."""
import uuid
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("loyalty", "0001_initial"),
        ("sales", "0005_reward_redemption_terms"),
        ("wallets", "0002_cashback_origin_entries"),
    ]
    operations = [
        migrations.AddField(
            model_name="loyaltyvoucher", name="reward",
            field=models.ForeignKey(
                to="sales.discountrewarddraft", on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name="loyalty_vouchers",
            ),
        ),
        migrations.AddField(model_name="loyaltyvoucher", name="minimum_order_cents",
            field=models.PositiveBigIntegerField(default=0)),
        migrations.AddField(model_name="loyaltyvoucher", name="allowed_channels",
            field=models.CharField(max_length=100, default="counter,vidalys_flow")),
        migrations.CreateModel(
            name="VoucherCashbackAllocation",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("amount_cents", models.PositiveBigIntegerField()),
                ("origin_event", models.ForeignKey(
                    to="wallets.cashbackevent", on_delete=django.db.models.deletion.PROTECT,
                    related_name="voucher_allocations",
                )),
                ("voucher", models.ForeignKey(
                    to="loyalty.loyaltyvoucher", on_delete=django.db.models.deletion.PROTECT,
                    related_name="cashback_allocations",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="vouchercashbackallocation",
            constraint=models.UniqueConstraint(
                fields=["voucher", "origin_event"], name="loyalty_cash_voucher_origin_once",
            ),
        ),
        migrations.AddConstraint(
            model_name="vouchercashbackallocation",
            constraint=models.CheckConstraint(
                condition=Q(amount_cents__gt=0), name="loyalty_cash_allocation_positive",
            ),
        ),
    ]
