"""Acesso por e-mail ao portal do consumidor: prova temporária, sem pontos."""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("participants", "0005_customer_link_approval")]

    operations = [
        migrations.CreateModel(
            name="MemberAccessChallenge",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                         editable=False, serialize=False)),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("submission", models.ForeignKey(
                    to="participants.enrollmentsubmission",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="member_access_challenges",
                )),
            ],
            options={"indexes": [models.Index(
                fields=["submission", "expires_at"],
                name="member_access_exp_idx",
            )]},
        ),
    ]
