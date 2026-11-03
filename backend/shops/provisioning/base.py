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
        ("configure_navigation", "Wyszukiwarka, kategorie i filtry"),
        ("generate_api_keys", "Generowanie kluczy API"),
        ("health_check", "Sprawdzanie działania sklepu"),
    ]

    def run_step(self, key, shop):
        getattr(self, f"step_{key}")(shop)

    def cleanup(self, shop):
        """Called after a failed run. Must be safe to call anytime."""

    def teardown(self, shop):
        """Remove everything the shop uses. Must be safe to call more than once."""

    def update_address(self, shop):
        """
        Move a running shop to its current `shop.url`, e.g. after SHOPS_BASE_DOMAIN changed.
        Returns the previous address, or None when there is nothing to move.
        """
        return None
