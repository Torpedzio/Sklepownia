from django.db import migrations


def seed(apps, schema_editor):
    Server = apps.get_model("shops", "Server")
    Server.objects.get_or_create(name="local", defaults={"hostname": "localhost"})


class Migration(migrations.Migration):
    dependencies = [
        ("shops", "0003_shopcredentials_changes"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
