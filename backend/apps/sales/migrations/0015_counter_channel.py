"""Canal balcão por loja. Lojas Nuvemshop começam só no site (balcão desligado); lojas sem
loja virtual continuam com balcão ligado, como funcionavam. Só acrescenta."""
from django.db import migrations, models


def keep_counter_for_physical_stores(apps, schema_editor):
    CounterPilot = apps.get_model("sales", "CounterPilot")
    CounterPilot.objects.exclude(tenant__platform="nuvemshop").update(counter_enabled=True)


class Migration(migrations.Migration):
    dependencies = [("sales", "0014_operation_mode")]
    operations = [
        migrations.AddField(model_name="counterpilot", name="counter_enabled",
                            field=models.BooleanField(default=False)),
        migrations.RunPython(keep_counter_for_physical_stores, migrations.RunPython.noop),
    ]
