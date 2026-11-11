import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="OAuthAttempt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, editable=False)),
                ("state_digest", models.CharField(max_length=64, unique=True)),
                ("session_digest", models.CharField(max_length=64)),
                ("client_id", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE)),
                ("user", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name="NuvemshopInstallation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, editable=False)),
                ("client_id", models.CharField(max_length=64)),
                ("store_id", models.CharField(max_length=64)),
                ("token_ciphertext", models.TextField()),
                ("scope", models.CharField(max_length=240)),
                ("connected_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("connected_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL)),
                ("tenant", models.OneToOneField(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE, related_name="nuvemshop_installation")),
            ],
        ),
        migrations.AddIndex(
            model_name="oauthattempt", index=models.Index(fields=["expires_at"], name="nuv_oauth_exp_idx"),
        ),
        migrations.AddConstraint(
            model_name="nuvemshopinstallation",
            constraint=models.UniqueConstraint(fields=("client_id", "store_id"), name="nuv_unique_app_store"),
        ),
    ]
