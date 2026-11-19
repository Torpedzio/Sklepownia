from django.db import migrations
from django.utils import timezone


def start_counting(apps, schema_editor):
    """The monitor raises the alarm when the nightly backups haven't run for a while: from now on."""
    Heartbeat = apps.get_model("monitoring", "Heartbeat")
    Heartbeat.objects.get_or_create(name="nightly-backups", defaults={"beat_at": timezone.now()})


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(start_counting, migrations.RunPython.noop),
    ]
