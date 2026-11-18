"""Campanhas inteligentes: modelo, período, público, grupo de comparação.
Só adiciona colunas com valor padrão; não altera dados existentes."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sales", "0007_counter_phone_digest")]
    operations = [
        migrations.AlterField(
            model_name="pointcampaigndraft", name="goal",
            field=models.CharField(choices=[
                ("second_purchase", "Segunda compra"), ("reactivation", "Recuperar clientes"),
                ("recurrence", "Estimular recorrência"), ("near_reward", "Quase lá"),
                ("multiplier", "Pontos em dobro"), ("birthday", "Aniversário"),
            ], max_length=24),
        ),
        migrations.AddField(model_name="pointcampaigndraft", name="title",
                            field=models.CharField(blank=True, default="", max_length=80)),
        migrations.AddField(model_name="pointcampaigndraft", name="message",
                            field=models.CharField(blank=True, default="", max_length=180)),
        migrations.AddField(model_name="pointcampaigndraft", name="starts_on",
                            field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="pointcampaigndraft", name="ends_on",
                            field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="pointcampaigndraft", name="window_days",
                            field=models.PositiveSmallIntegerField(default=30)),
        migrations.AddField(model_name="pointcampaigndraft", name="inactive_days",
                            field=models.PositiveSmallIntegerField(default=60)),
        migrations.AddField(model_name="pointcampaigndraft", name="near_points",
                            field=models.PositiveIntegerField(default=100)),
        migrations.AddField(model_name="pointcampaigndraft", name="multiplier",
                            field=models.PositiveSmallIntegerField(default=2)),
        migrations.AddField(model_name="pointcampaigndraft", name="holdout_percent",
                            field=models.PositiveSmallIntegerField(default=10)),
        migrations.AddField(model_name="pointcampaigndraft", name="published_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddConstraint(
            model_name="pointcampaigndraft",
            constraint=models.CheckConstraint(condition=models.Q(holdout_percent__lte=50),
                                              name="point_campaign_holdout_max"),
        ),
    ]
