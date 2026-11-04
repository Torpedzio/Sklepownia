class ProvisioningError(Exception):
    pass


class BaseProvisioner:
    """
    Sets up a WordPress + WooCommerce shop step by step.

    Every step must be idempotent: a retry creates a new job and runs all steps
    again, so a step has to cope with work left behind by a failed attempt.
    Implementations define a `step_<key>(shop)` method for each step.
    """

    # Labels are shown to shop owners, so they say what the shop gets, not how it's done.
    STEPS = [
        ("allocate_server", "Miejsce na serwerze"),
        ("create_database", "Baza produktów i zamówień"),
        ("start_container", "Uruchomienie sklepu"),
        ("install_wordpress", "Strona i konto administratora"),
        ("configure_locale", "Język i strefa czasowa"),
        ("configure_woocommerce", "Waluta, koszyk i zamówienia"),
        ("install_theme", "Wygląd sklepu"),
        ("create_categories", "Kategorie produktów"),
        ("configure_navigation", "Wyszukiwarka i filtry"),
        ("generate_api_keys", "Połączenie z aplikacją"),
        ("health_check", "Końcowe sprawdzenie"),
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
