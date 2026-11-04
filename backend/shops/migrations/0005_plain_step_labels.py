from django.db import migrations

# Plain-language step labels. Existing jobs keep their labels in the database, so update them too.
LABELS = {
    "allocate_server": ("Przydzielanie serwera", "Miejsce na serwerze"),
    "create_database": ("Tworzenie bazy danych", "Baza produktów i zamówień"),
    "start_container": ("Uruchamianie WordPressa", "Uruchomienie sklepu"),
    "install_wordpress": ("Instalacja WordPressa", "Strona i konto administratora"),
    "configure_locale": ("Ustawienia języka i regionu", "Język i strefa czasowa"),
    "configure_woocommerce": ("Konfiguracja WooCommerce", "Waluta, koszyk i zamówienia"),
    "install_theme": ("Instalacja motywu", "Wygląd sklepu"),
    "create_categories": ("Tworzenie kategorii", "Kategorie produktów"),
    "configure_navigation": ("Wyszukiwarka, kategorie i filtry", "Wyszukiwarka i filtry"),
    "generate_api_keys": ("Generowanie kluczy API", "Połączenie z aplikacją"),
    "health_check": ("Sprawdzanie działania sklepu", "Końcowe sprawdzenie"),
}


def relabel(apps, schema_editor, column):
    ProvisioningStep = apps.get_model("shops", "ProvisioningStep")
    for key, labels in LABELS.items():
        ProvisioningStep.objects.filter(key=key).update(label=labels[column])


class Migration(migrations.Migration):
    dependencies = [("shops", "0004_seed_local_server")]

    operations = [
        migrations.RunPython(
            lambda apps, schema_editor: relabel(apps, schema_editor, 1),
            lambda apps, schema_editor: relabel(apps, schema_editor, 0),
        ),
    ]
