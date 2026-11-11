"""Vínculo de consentimento e cliente da loja com aprovação explícita."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("participants", "0004_enrollment_email_proof"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(
            model_name="enrollmentsubmission", name="status",
            field=models.CharField(max_length=32, default="pending_verification",
                                   choices=[
                                       ("pending_verification", "Aguardando verificação"),
                                       ("email_verified", "E-mail confirmado"),
                                       ("linked", "Vínculo com a loja aprovado"),
                                       ("withdrawn", "Solicitação retirada"),
                                   ]),
        ),
        migrations.CreateModel(
            name="EnrollmentCustomerLink",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False)),
                ("external_customer_id", models.CharField(max_length=64)),
                ("confirmed_at", models.DateTimeField(auto_now_add=True)),
                ("source", models.CharField(max_length=40,
                    default="nuvemshop_customer_email_match")),
                ("confirmed_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name="+")),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="customer_enrollment_links")),
                ("submission", models.OneToOneField(to="participants.enrollmentsubmission",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="customer_link")),
                ("participant", models.OneToOneField(to="participants.programparticipant",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="enrollment_link")),
            ],
        ),
        migrations.AddConstraint(
            model_name="enrollmentcustomerlink",
            constraint=models.UniqueConstraint(
                fields=["tenant", "external_customer_id"],
                name="loyalty_unique_verified_customer_link"),
        ),
    ]
