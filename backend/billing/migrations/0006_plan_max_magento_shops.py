from django.db import migrations, models

COMMON = [
    "Ustawienia płatności, wysyłki i podatków w aplikacji",
    "Dane do panelu sklepu e-mailem",
]

PLANS = {
    "start": {
        "max_magento_shops": 0,
        "features": [
            "1 sklep na WooCommerce albo PrestaShop",
            "Sklep w osobnym kontenerze z własną bazą",
            *COMMON,
            "Pomoc e-mailowa",
        ],
    },
    "standard": {
        "max_magento_shops": 1,
        "features": [
            "Do 3 sklepów na WooCommerce, PrestaShop albo Magento",
            "W tym 1 sklep na Magento",
            "Każdy sklep w osobnym kontenerze z własną bazą",
            *COMMON,
            "Pomoc e-mailowa",
        ],
    },
    "business": {
        "max_magento_shops": 5,
        "features": [
            "Do 10 sklepów na WooCommerce, PrestaShop albo Magento",
            "W tym do 5 sklepów na Magento",
            "Dwa razy więcej pamięci dla każdego sklepu (1 GB): sprawniej przy większym ruchu",
            "Każdy sklep w osobnym kontenerze z własną bazą",
            *COMMON,
            "Priorytetowa pomoc: odpowiedź w ciągu 1 dnia roboczego",
        ],
    },
}


def set_limits(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for code, fields in PLANS.items():
        Plan.objects.filter(code=code).update(**fields)


class Migration(migrations.Migration):
    dependencies = [("billing", "0005_plan_changes_and_credit")]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="max_magento_shops",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(set_limits, migrations.RunPython.noop),
    ]
