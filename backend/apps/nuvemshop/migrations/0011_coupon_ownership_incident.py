"""PR29: append-only ownership event; review requires authorized workflow."""
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0010_verified_unused_before_revocation")]
    operations = [
        migrations.AlterField(
            model_name="nuvemshopcouponintent",
            name="state",
            field=models.CharField(
                max_length=24, default="prepared",
                choices=[
                    ("prepared","Preparado"), ("uncertain","Resultado HTTP desconhecido"),
                    ("issued","Criado no provedor"),
                    ("applied_pending_proof","Aplicado, captura não comprovada"),
                    ("settled","Baixa financeira validada"),
                    ("revoking","Revogação externa em progresso"),
                    ("revoked","Revogação externa confirmada"),
                    ("ownership_violation","Possível uso por terceiro"),
                ],
            ),
        ),
        migrations.CreateModel(
            name="NuvemshopCouponOwnershipIncident",
            fields=[
                ("id",models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False,serialize=False)),
                ("order_digest",models.CharField(max_length=64)),
                ("reason",models.CharField(max_length=32,default="identity_mismatch")),
                ("created_at",models.DateTimeField(auto_now_add=True)),
                ("reviewed_at",models.DateTimeField(null=True,blank=True)),
                ("intent",models.OneToOneField(to="nuvemshop.nuvemshopcouponintent",
                    related_name="ownership_incident",on_delete=django.db.models.deletion.PROTECT)),
                ("tenant",models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT)),
            ],
            options={"indexes":[models.Index(
                fields=["tenant","reviewed_at"],name="coupon_incident_review_idx"
            )]},
        ),
    ]
