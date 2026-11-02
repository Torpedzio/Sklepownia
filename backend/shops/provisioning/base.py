class ProvisioningError(Exception):
    pass


class BaseProvisioner:
    """
    Sets up a WordPress + WooCommerce shop step by step.

    Every step must be idempotent: a retry creates a new job and runs all steps
    again, so a step has to cope with work left behind by a failed attempt.
    Implementations define a `step_<key>(shop)` method for each step.
    """

    STEPS = [
        ("allocate_server", "Przydzielanie serwera"),
        ("create_database", "Tworzenie bazy danych"),
        ("start_container", "Uruchamianie WordPressa"),
        ("install_wordpress", "Instalacja WordPressa"),
        ("configure_locale", "Ustawienia języka i regionu"),
        ("configure_woocommerce", "Konfiguracja WooCommerce"),
        ("install_theme", "Instalacja motywu"),
        ("create_categories", "Tworzenie kategorii"),
        ("generate_api_keys", "Generowanie kluczy API"),
        ("health_check", "Sprawdzanie działania sklepu"),
    ]

    def run_step(self, key, shop):
        getattr(self, f"step_{key}")(shop)

    def cleanup(self, shop):
        """Remove resources left behind by a failed run. Must be safe to call anytime."""
