"""Termos, convite de uso único e aceite aguardando verificação de identidade."""
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("participants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="ProgramTerms",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.CharField(max_length=40)),
                ("title", models.CharField(max_length=100)),
                ("body", models.TextField(max_length=4000)),
                ("active", models.BooleanField(default=True)),
                ("approved_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("approved_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name="+")),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.CASCADE, related_name="loyalty_terms")),
            ],
            options={"ordering": ["-approved_at", "-id"]},
        ),
        migrations.CreateModel(
            name="EnrollmentInvite",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name="+")),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.CASCADE, related_name="loyalty_invitations")),
                ("terms", models.ForeignKey(to="participants.programterms",
                    on_delete=django.db.models.deletion.PROTECT, related_name="invitations")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="EnrollmentSubmission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=140)),
                ("email", models.EmailField(max_length=254)),
                ("terms_digest", models.CharField(max_length=64)),
                ("accepted_at", models.DateTimeField()),
                ("marketing_opt_in", models.BooleanField(default=False)),
                ("status", models.CharField(max_length=32, default="pending_verification",
                    choices=[("pending_verification", "Aguardando verificação")])),
                ("invitation", models.OneToOneField(to="participants.enrollmentinvite",
                    on_delete=django.db.models.deletion.PROTECT, related_name="submission")),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.CASCADE, related_name="loyalty_submissions")),
                ("terms", models.ForeignKey(to="participants.programterms",
                    on_delete=django.db.models.deletion.PROTECT, related_name="submissions")),
            ],
            options={"ordering": ["-accepted_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="programterms",
            constraint=models.UniqueConstraint(fields=["tenant","version"],
                name="loyalty_terms_version_unique"),
        ),
        migrations.AddConstraint(
            model_name="programterms",
            constraint=models.UniqueConstraint(fields=["tenant"],condition=Q(active=True),
                name="loyalty_single_active_terms"),
        ),
    ]
