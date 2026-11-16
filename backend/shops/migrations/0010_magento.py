from django.db import migrations, models

MAGENTO_TEMPLATES = [
    {
        "slug": "luma",
        "platform": "magento",
        "name": "Luma",
        "description": "Domyślny motyw Magento: duże zdjęcia, menu kategorii i filtry z boku listy produktów.",
        "theme": "Magento/luma",
        "sort_order": 20,
    },
]

PLATFORM_CHOICES = [("woocommerce", "WooCommerce"), ("prestashop", "PrestaShop"), ("magento", "Magento")]


def seed(apps, schema_editor):
    ShopTemplate = apps.get_model("shops", "ShopTemplate")
    for template in MAGENTO_TEMPLATES:
        ShopTemplate.objects.update_or_create(slug=template["slug"], defaults=template)


def unseed(apps, schema_editor):
    ShopTemplate = apps.get_model("shops", "ShopTemplate")
    ShopTemplate.objects.filter(slug__in=[t["slug"] for t in MAGENTO_TEMPLATES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shops", "0009_platforms"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shop",
            name="platform",
            field=models.CharField(choices=PLATFORM_CHOICES, default="woocommerce", max_length=20),
        ),
        migrations.AlterField(
            model_name="shoptemplate",
            name="platform",
            field=models.CharField(choices=PLATFORM_CHOICES, default="woocommerce", max_length=20),
        ),
        migrations.RunPython(seed, unseed),
    ]
