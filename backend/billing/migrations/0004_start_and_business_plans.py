from decimal import Decimal

from django.db import migrations

COMMON = [
    "Ustawienia płatności, wysyłki i podatków w aplikacji",
    "Dane do panelu WordPressa e-mailem",
]

PLANS = {
    "start": {
        "name": "Start",
        "description": "Jeden sklep na początek sprzedaży w internecie.",
        "price": Decimal("29.00"),
        "max_shops": 1,
        "shop_memory_mb": 512,
        "sort_order": 10,
        "features": [
            "1 sklep na WordPressie z WooCommerce",
            "Sklep w osobnym kontenerze z własną bazą",
            *COMMON,
            "Pomoc e-mailowa",
        ],
    },
    "standard": {
        "sort_order": 20,
        "is_featured": True,
        "features": [
            "Do 3 sklepów na WordPressie z WooCommerce",
            "Każdy sklep w osobnym kontenerze z własną bazą",
            *COMMON,
            "Pomoc e-mailowa",
        ],
    },
    "business": {
        "name": "Biznes",
        "description": "Dla firm z kilkoma markami albo większym ruchem.",
        "price": Decimal("99.00"),
        "max_shops": 10,
        "shop_memory_mb": 1024,
        "sort_order": 30,
        "features": [
            "Do 10 sklepów na WordPressie z WooCommerce",
            "Dwa razy więcej pamięci dla każdego sklepu (1 GB): sprawniej przy większym ruchu",
            "Każdy sklep w osobnym kontenerze z własną bazą",
            *COMMON,
            "Priorytetowa pomoc: odpowiedź w ciągu 1 dnia roboczego",
        ],
    },
}


def add_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for code, fields in PLANS.items():
        if code == "standard":
            Plan.objects.filter(code=code).update(**fields)
        else:
            Plan.objects.get_or_create(code=code, defaults=fields)


def remove_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    # Plans someone has paid for stay: payments and subscriptions point at them.
    Plan.objects.filter(code__in=["start", "business"], subscriptions__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_plan_memory_and_featured")]

    operations = [migrations.RunPython(add_plans, remove_plans)]
