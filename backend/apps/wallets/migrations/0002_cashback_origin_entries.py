"""Rastreabilidade imutável do cashback por crédito de compra."""
import uuid
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("wallets", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="CashbackOriginEntry",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("bucket", models.CharField(max_length=12, choices=[
                    ("pending", "Pendente"), ("available", "Liberado no ledger"),
                    ("reserved", "Reservado no ledger"),
                ])),
                ("delta_cents", models.BigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.ForeignKey(
                    to="wallets.cashbackevent", on_delete=django.db.models.deletion.PROTECT,
                    related_name="origin_entries",
                )),
                ("origin_event", models.ForeignKey(
                    to="wallets.cashbackevent", on_delete=django.db.models.deletion.PROTECT,
                    related_name="origin_movements",
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="cashbackoriginentry",
            constraint=models.UniqueConstraint(
                fields=["event", "bucket"], name="cashback_origin_event_bucket_once",
            ),
        ),
        migrations.AddConstraint(
            model_name="cashbackoriginentry",
            constraint=models.CheckConstraint(
                condition=~Q(delta_cents=0), name="cashback_origin_entry_nonzero",
            ),
        ),
    ]
