"""
E-commerce systems a shop can run on, and what differs between them for the platform:
the setup steps the owner watches, which settings the app can change and where the admin panel is.
"""

from dataclasses import dataclass

from django.db import models


class Platform(models.TextChoices):
    WOOCOMMERCE = "woocommerce", "WooCommerce"
    PRESTASHOP = "prestashop", "PrestaShop"
    MAGENTO = "magento", "Magento"


@dataclass(frozen=True)
class PlatformInfo:
    description: str
    # Name of the admin panel as owners know it, e.g. "panel WordPressa".
    panel_name: str
    # (key, label) of every setup step; the provisioner has a `step_<key>` method for each.
    # Labels are shown to shop owners, so they say what the shop gets, not how it's done.
    steps: list
    # Settings sections (shops/shop_settings.py) the app can change on this platform.
    settings_sections: tuple
    # Path of the admin panel, when it's the same for every shop (PrestaShop gives each shop its own).
    admin_path: str = ""
    # How long setting up takes, as the app says it: "To potrwa <setup_time>".
    setup_time: str = "około dwóch minut"


ALL_SECTIONS = ("general", "availability", "shopping", "payments", "shipping", "taxes", "region", "appearance")

PLATFORMS = {
    Platform.WOOCOMMERCE: PlatformInfo(
        description="WordPress z wtyczką WooCommerce. Najpopularniejszy sklep na świecie, tysiące wtyczek i motywów.",
        panel_name="panel WordPressa",
        steps=[
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
        ],
        settings_sections=ALL_SECTIONS,
        admin_path="wp-admin",
    ),
    Platform.PRESTASHOP: PlatformInfo(
        description="Samodzielny system sklepowy, popularny w Polsce. Rozbudowany katalog i zamówienia od razu w panelu.",
        panel_name="panel PrestaShop",
        steps=[
            ("allocate_server", "Miejsce na serwerze"),
            ("create_database", "Baza produktów i zamówień"),
            ("start_container", "Uruchomienie sklepu"),
            ("install_prestashop", "Sklep, język i konto administratora"),
            ("configure_shop", "Waluta, koszyk i zamówienia"),
            ("create_categories", "Kategorie produktów"),
            ("configure_navigation", "Menu, wyszukiwarka i filtry"),
            ("health_check", "Końcowe sprawdzenie"),
        ],
        # Shipping, taxes, region and the shopping rules are set in the PrestaShop panel for now.
        settings_sections=("general", "availability", "payments", "appearance"),
    ),
    Platform.MAGENTO: PlatformInfo(
        description="System dla dużych sklepów: rozbudowany katalog, wiele magazynów i wersji językowych. "
        "Potrzebuje więcej pamięci serwera.",
        panel_name="panel Magento",
        steps=[
            ("allocate_server", "Miejsce na serwerze"),
            ("create_database", "Baza produktów i zamówień"),
            ("start_container", "Uruchomienie sklepu"),
            ("install_magento", "Sklep, język i konto administratora"),
            ("configure_shop", "Waluta, płatności i dostawa"),
            ("create_categories", "Kategorie produktów"),
            ("configure_navigation", "Menu, wyszukiwarka i filtry"),
            ("health_check", "Końcowe sprawdzenie"),
        ],
        # Opening and closing the shop, the shopping rules and the theme are set in the Magento panel.
        settings_sections=("general", "payments", "shipping", "taxes", "region"),
        setup_time="około minuty",
    ),
}


def platform_info(platform) -> PlatformInfo:
    return PLATFORMS[Platform(platform)]
