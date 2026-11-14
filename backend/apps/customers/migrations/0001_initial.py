import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0003_unconnected_merchant_tenants"),
        ("participants", "0007_standalone_participant"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerProfile",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("display_name", models.CharField(max_length=140, blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("participant", models.OneToOneField(
                    to="participants.programparticipant", on_delete=django.db.models.deletion.PROTECT,
                    null=True, blank=True, related_name="customer_profile",
                )),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant", on_delete=django.db.models.deletion.PROTECT,
                    related_name="customer_profiles",
                )),
            ],
            options={"indexes": [
                models.Index(fields=["tenant", "created_at"], name="cust_profile_tenant_idx"),
            ]},
        ),
        migrations.CreateModel(
            name="VerifiedCustomerContact",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("kind", models.CharField(max_length=8, choices=[("email", "E-mail"), ("phone", "Telefone E.164")])),
                ("lookup_digest", models.CharField(max_length=64)),
                ("proof_method", models.CharField(max_length=32)),
                ("verified_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("profile", models.ForeignKey(
                    to="customers.customerprofile", on_delete=django.db.models.deletion.PROTECT,
                    related_name="verified_contacts",
                )),
                ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.CreateModel(
            name="ChannelCustomerReference",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("channel", models.CharField(
                    max_length=24, choices=[
                        ("nuvemshop", "Nuvemshop"), ("vidalys_flow", "Vidalys Flow"),
                        ("counter", "Balcão"), ("whatsapp", "WhatsApp"),
                    ],
                )),
                ("external_id", models.CharField(max_length=120)),
                ("linked_at", models.DateTimeField(auto_now_add=True)),
                ("profile", models.ForeignKey(
                    to="customers.customerprofile", on_delete=django.db.models.deletion.PROTECT,
                    related_name="channel_references",
                )),
                ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.AddConstraint(
            model_name="verifiedcustomercontact",
            constraint=models.UniqueConstraint(
                fields=("tenant", "kind", "lookup_digest"), name="cust_verified_contact_once",
            ),
        ),
        migrations.AddConstraint(
            model_name="channelcustomerreference",
            constraint=models.UniqueConstraint(
                fields=("tenant", "channel", "external_id"), name="cust_channel_external_once",
            ),
        ),
    ]
