from django.db import migrations

TEMPLATES = [
    {
        "slug": "storefront",
        "name": "Storefront",
        "description": "Oficjalny, prosty motyw WooCommerce. Dobry punkt wyjścia dla każdego sklepu.",
        "wp_theme": "storefront",
        "sort_order": 0,
    },
    {
        "slug": "astra",
        "name": "Astra",
        "description": "Lekki i szybki motyw z wieloma gotowymi układami.",
        "wp_theme": "astra",
        "sort_order": 1,
    },
    {
        "slug": "kadence",
        "name": "Kadence",
        "description": "Nowoczesny motyw z rozbudowanymi opcjami wyglądu.",
        "wp_theme": "kadence",
        "sort_order": 2,
    },
]


def seed(apps, schema_editor):
    ShopTemplate = apps.get_model("shops", "ShopTemplate")
    for template in TEMPLATES:
        ShopTemplate.objects.update_or_create(slug=template["slug"], defaults=template)


def unseed(apps, schema_editor):
    ShopTemplate = apps.get_model("shops", "ShopTemplate")
    ShopTemplate.objects.filter(slug__in=[t["slug"] for t in TEMPLATES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shops", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
