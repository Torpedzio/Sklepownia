from django.db import migrations, models

# Limit of staff per shop and the pricing line about it, placed after the lines about shops.
PLANS = {
    "start": (5, "Do 5 osób z obsługi sklepu", 1),
    "standard": (20, "Do 20 osób z obsługi w każdym sklepie", 2),
    "business": (None, "Obsługa sklepów bez limitu osób", 2),
}


def set_limits(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for code, (limit, feature, position) in PLANS.items():
        plan = Plan.objects.filter(code=code).first()
        if plan is None:
            continue
        plan.max_staff = limit
        if feature not in plan.features:
            plan.features = [*plan.features[:position], feature, *plan.features[position:]]
        plan.save(update_fields=["max_staff", "features"])


class Migration(migrations.Migration):
    dependencies = [("billing", "0007_invoices")]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="max_staff",
            field=models.PositiveSmallIntegerField(
                blank=True, help_text="Osoby z obsługi w każdym sklepie, bez właściciela; puste: bez limitu.", null=True,
            ),
        ),
        migrations.RunPython(set_limits, migrations.RunPython.noop),
    ]
