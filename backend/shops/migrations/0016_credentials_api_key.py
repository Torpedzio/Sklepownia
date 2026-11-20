from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0015_backups"),
    ]

    operations = [
        migrations.RenameField(
            model_name="shopcredentials",
            old_name="wp_application_password",
            new_name="api_key",
        ),
    ]
