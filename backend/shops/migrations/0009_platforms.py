from django.db import migrations, models

PRESTASHOP_TEMPLATES = [
    {
        "slug": "hummingbird",
        "platform": "prestashop",
        "name": "Hummingbird",
        "description": "Nowy, domyślny motyw PrestaShop 9. Lekki, czytelny i dopracowany na telefonach.",
        "theme": "hummingbird",
        "sort_order": 10,
    },
    {
        "slug": "classic",
        "platform": "prestashop",
        "name": "Classic",
        "description": "Sprawdzony motyw PrestaShop z menu kategorii i filtrami z boku listy produktów.",
        "theme": "classic",
        "sort_order": 11,
    },
]


def seed(apps, schema_editor):
    ShopTemplate = apps.get_model("shops", "ShopTemplate")
    for template in PRESTASHOP_TEMPLATES:
        ShopTemplate.objects.update_or_create(slug=template["slug"], defaults=template)


def unseed(apps, schema_editor):
    ShopTemplate = apps.get_model("shops", "ShopTemplate")
    ShopTemplate.objects.filter(slug__in=[t["slug"] for t in PRESTASHOP_TEMPLATES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shops", "0008_suspended_label"),
    ]

    operations = [
        # Shops so far all run WooCommerce, which is the default for both new fields.
        migrations.AddField(
            model_name="shop",
            name="platform",
            field=models.CharField(
                choices=[("woocommerce", "WooCommerce"), ("prestashop", "PrestaShop")],
                default="woocommerce",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="shop",
            name="admin_path",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="shoptemplate",
            name="platform",
            field=models.CharField(
                choices=[("woocommerce", "WooCommerce"), ("prestashop", "PrestaShop")],
                default="woocommerce",
                max_length=20,
            ),
        ),
        migrations.RenameField(model_name="shoptemplate", old_name="wp_theme", new_name="theme"),
        migrations.RenameField(model_name="shopcredentials", old_name="wp_admin_username", new_name="admin_login"),
        migrations.RenameField(model_name="shopcredentials", old_name="wp_admin_password", new_name="admin_password"),
        # A PrestaShop login is an e-mail address.
        migrations.AlterField(
            model_name="shopcredentials",
            name="admin_login",
            field=models.CharField(max_length=254),
        ),
        migrations.RunPython(seed, unseed),
    ]
