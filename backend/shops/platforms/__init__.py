"""Supported e-commerce systems and what differs between them: setup steps, editable settings, admin panel."""

from dataclasses import dataclass

from django.db import models


class Platform(models.TextChoices):
    WOOCOMMERCE = "woocommerce", "WooCommerce"
    PRESTASHOP = "prestashop", "PrestaShop"
    MAGENTO = "magento", "Magento"


@dataclass(frozen=True)
class PlatformInfo:
    description: str
    # As owners know it, e.g. "panel WordPressa".
    panel_name: str
    # (key, label) per setup step, run by the provisioner's `step_<key>`. Labels are shown to owners: what the shop
    # gets, not how it's done.
    steps: list
    # Sections of shops/shop_settings.py the app can change here.
    settings_sections: tuple
    # shop_settings.OPERATORS the app sets up in the payments section.
    payment_operators: tuple = ()
    # When the same for every shop (PrestaShop gives each shop its own).
    admin_path: str = ""
    # Shown as "To potrwa <setup_time>".
    setup_time: str = "około dwóch minut"


ALL_SECTIONS = (
    "general", "availability", "shopping", "payments", "shipping", "taxes", "region", "appearance", "documents",
)

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
        payment_operators=("przelewy24", "payu"),
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
            ("generate_api_keys", "Połączenie z aplikacją"),
            ("health_check", "Końcowe sprawdzenie"),
        ],
        # Shipping, taxes, region and the shopping rules are set in the PrestaShop panel for now.
        settings_sections=("general", "availability", "payments", "appearance", "documents"),
        payment_operators=("przelewy24", "payu"),
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
            ("generate_api_keys", "Połączenie z aplikacją"),
            ("health_check", "Końcowe sprawdzenie"),
        ],
        # Opening/closing, shopping rules, theme and (for now) online payments are set in the Magento panel.
        settings_sections=("general", "payments", "shipping", "taxes", "region", "documents"),
        setup_time="około minuty",
    ),
}


def platform_info(platform) -> PlatformInfo:
    return PLATFORMS[Platform(platform)]
