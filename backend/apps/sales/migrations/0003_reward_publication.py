"""Publicação informativa de recompensas; não ativa pontos ou cupons."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0002_benefit_drafts"),
    ]

    operations = [
        migrations.AddField(
            model_name="discountrewarddraft",
            name="publication_status",
            field=models.CharField(
                max_length=12, default="draft",
                choices=[("draft", "Rascunho"), ("published", "Publicado para consulta")],
            ),
        ),
        migrations.AddField(
            model_name="discountrewarddraft",
            name="published_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
