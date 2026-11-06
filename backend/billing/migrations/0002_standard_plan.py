from decimal import Decimal

from django.db import migrations


def add_standard_plan(apps, schema_editor):
    apps.get_model("billing", "Plan").objects.get_or_create(
        code="standard",
        defaults={
            "name": "Standard",
            "description": "Wszystko, czego potrzebuje mały sklep internetowy.",
            "price": Decimal("49.00"),
            "max_shops": 3,
            "features": [
                "Do 3 sklepów na WordPressie z WooCommerce",
                "Każdy sklep w osobnym kontenerze z własną bazą",
                "Ustawienia płatności, wysyłki i podatków w aplikacji",
                "Pomoc e-mailowa",
            ],
        },
    )


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [migrations.RunPython(add_standard_plan, migrations.RunPython.noop)]
