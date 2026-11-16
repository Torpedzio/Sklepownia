"""
Shop settings the owner can change in the app, grouped in sections as the app shows them.

The section serializers below are the schema: they validate input, give every field its label
(shown in the change history) and turn values into plain JSON (money as "15.00").
"""

import re
from decimal import Decimal

from rest_framework import serializers

from .choices import COUNTRY_TIMEZONES, VAT_RATES, Country, Currency, Language, Timezone
from .models import ShopTemplate

MONEY = {"max_digits": 10, "decimal_places": 2, "min_value": Decimal("0")}


class GeneralSection(serializers.Serializer):
    name = serializers.CharField(label="Nazwa sklepu", min_length=2, max_length=100)
    description = serializers.CharField(label="Opis sklepu", max_length=500, allow_blank=True)
    contact_email = serializers.EmailField(label="E-mail kontaktowy")


class AvailabilitySection(serializers.Serializer):
    is_open = serializers.BooleanField(label="Sklep otwarty")


class ShoppingSection(serializers.Serializer):
    guest_checkout = serializers.BooleanField(label="Zakupy bez zakładania konta")
    signup_at_checkout = serializers.BooleanField(label="Zakładanie konta przy zamówieniu")
    reviews = serializers.BooleanField(label="Opinie o produktach")
    manage_stock = serializers.BooleanField(label="Pilnowanie stanów magazynowych")
    low_stock_threshold = serializers.IntegerField(label="Próg „kończy się”", min_value=0, max_value=10000)


class PaymentsSection(serializers.Serializer):
    bank_transfer_enabled = serializers.BooleanField(label="Przelew tradycyjny")
    bank_account_name = serializers.CharField(label="Odbiorca przelewu", max_length=100, allow_blank=True)
    bank_account_number = serializers.CharField(label="Numer konta", max_length=42, allow_blank=True)
    bank_name = serializers.CharField(label="Nazwa banku", max_length=100, allow_blank=True)
    cash_on_delivery_enabled = serializers.BooleanField(label="Płatność przy odbiorze")

    def validate_bank_account_number(self, value):
        number = re.sub(r"[\s-]", "", value).upper()
        if not number:
            return ""
        if not re.fullmatch(r"[A-Z0-9]{8,34}", number):
            raise serializers.ValidationError("Numer konta może zawierać tylko litery i cyfry.")
        # A Polish account number (26 digits) is an IBAN without the country code.
        iban = "PL" + number if re.fullmatch(r"\d{26}", number) else number
        if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", iban) and not _iban_checksum_ok(iban):
            raise serializers.ValidationError("Ten numer konta ma błąd. Sprawdź, czy nie brakuje cyfry.")
        return _group(number)


class ShippingSection(serializers.Serializer):
    courier_enabled = serializers.BooleanField(label="Kurier")
    courier_cost = serializers.DecimalField(label="Cena wysyłki kurierem", **MONEY)
    free_shipping_enabled = serializers.BooleanField(label="Darmowa dostawa")
    free_shipping_min_amount = serializers.DecimalField(label="Darmowa dostawa od kwoty", **MONEY)
    local_pickup_enabled = serializers.BooleanField(label="Odbiór osobisty")


class TaxesSection(serializers.Serializer):
    enabled = serializers.BooleanField(label="Naliczanie podatku VAT")
    prices_include_tax = serializers.BooleanField(label="Ceny brutto")
    standard_rate = serializers.DecimalField(
        label="Stawka VAT", max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("50"),
    )


class RegionSection(serializers.Serializer):
    language = serializers.ChoiceField(label="Język sklepu", choices=Language.choices)
    currency = serializers.ChoiceField(label="Waluta", choices=Currency.choices)
    country = serializers.ChoiceField(label="Kraj", choices=Country.choices)
    timezone = serializers.ChoiceField(label="Strefa czasowa", choices=Timezone.choices)


class AppearanceSection(serializers.Serializer):
    theme = serializers.SlugRelatedField(
        label="Motyw", slug_field="slug", queryset=ShopTemplate.objects.filter(is_active=True),
    )


# Order of the sections in the app and when applying changes.
SECTIONS = {
    "general": GeneralSection,
    "availability": AvailabilitySection,
    "shopping": ShoppingSection,
    "payments": PaymentsSection,
    "shipping": ShippingSection,
    "taxes": TaxesSection,
    "region": RegionSection,
    "appearance": AppearanceSection,
}

FIELD_LABELS = {
    section: {name: str(field.label) for name, field in serializer().fields.items()}
    for section, serializer in SECTIONS.items()
}


def default_settings(shop):
    """Settings of a freshly provisioned shop, used until the shop has been read for the first time."""
    config = shop.config
    return {
        "general": {"name": shop.name, "description": config.description, "contact_email": config.contact_email},
        "availability": {"is_open": True},
        "shopping": {
            "guest_checkout": True,
            "signup_at_checkout": False,
            "reviews": True,
            "manage_stock": True,
            "low_stock_threshold": 2,
        },
        "payments": {
            "bank_transfer_enabled": False,
            "bank_account_name": "",
            "bank_account_number": "",
            "bank_name": "",
            "cash_on_delivery_enabled": False,
        },
        "shipping": {
            "courier_enabled": False,
            "courier_cost": "15.00",
            "free_shipping_enabled": False,
            "free_shipping_min_amount": "200.00",
            "local_pickup_enabled": False,
        },
        "taxes": {
            "enabled": False,
            "prices_include_tax": True,
            "standard_rate": suggested_vat_rate(config.country),
        },
        "region": {
            "language": config.language,
            "currency": config.currency,
            "country": config.country,
            "timezone": COUNTRY_TIMEZONES.get(config.country, Timezone.UTC.value),
        },
        "appearance": {"theme": config.template.slug},
    }


def suggested_vat_rate(country):
    return VAT_RATES.get(country, ["0.00"])[0]


def complete(values, defaults):
    """`values` with every section and field present, missing ones taken from `defaults`."""
    return {section: {**fields, **values.get(section, {})} for section, fields in defaults.items()}


class SettingsUpdateSerializer(serializers.Serializer):
    """
    Partial update (use with `partial=True`): any sections, and any fields within them. Rules spanning
    several fields are checked against the settings as they will be after the change
    (`context["current"]` merged with the input).
    """

    def get_fields(self):
        return {name: section(required=False) for name, section in SECTIONS.items()}

    def validate(self, attrs):
        errors = {}
        # The platform's sections (context["sections"]); themes belong to one platform too.
        sections = self.context.get("sections", SECTIONS)
        for section in attrs:
            if section not in sections:
                errors[section] = ["Tę część ustawień zmienisz w panelu sklepu."]
        theme = attrs.get("appearance", {}).get("theme")
        platform = self.context.get("platform")
        if theme is not None and platform and theme.platform != platform:
            errors["appearance"] = {"theme": ["Ten motyw nie pasuje do platformy sklepu."]}
        if errors:
            raise serializers.ValidationError(errors)
        merged = merge(self.context["current"], normalize(attrs))
        payments = merged["payments"]
        if payments["bank_transfer_enabled"]:
            missing = {
                field: ["Podaj, żeby klienci wiedzieli, gdzie przelać pieniądze."]
                for field in ("bank_account_name", "bank_account_number")
                if not payments[field]
            }
            if missing:
                errors["payments"] = missing
        shopping = merged["shopping"]
        if not shopping["guest_checkout"] and not shopping["signup_at_checkout"]:
            errors["shopping"] = {
                "guest_checkout": ["Klienci muszą móc kupić bez konta albo założyć je przy zamówieniu."],
            }
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def normalize(validated):
    """Validated input as plain JSON values, in the same form as the stored settings."""
    result = {}
    for section, fields in validated.items():
        schema = SECTIONS[section]().fields
        result[section] = {name: schema[name].to_representation(value) for name, value in fields.items()}
    return result


def merge(current, changes):
    return {section: {**fields, **changes.get(section, {})} for section, fields in current.items()}


def diff(current, changes):
    """Only the fields whose value actually changes, {section: {field: new value}}."""
    result = {}
    for section, fields in changes.items():
        changed = {name: value for name, value in fields.items() if current.get(section, {}).get(name) != value}
        if changed:
            result[section] = changed
    return result


def describe(changes):
    """Labels of the changed fields, in section order, e.g. ["Nazwa sklepu", "Waluta"]."""
    return [
        FIELD_LABELS[section][name]
        for section in SECTIONS
        for name in FIELD_LABELS[section]
        if name in changes.get(section, {})
    ]


def _iban_checksum_ok(iban):
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    return int(digits) % 97 == 1


def _group(number):
    """Account numbers read best in groups of four, like on a bank statement."""
    if re.fullmatch(r"\d{26}", number):
        return number[:2] + " " + " ".join(number[i:i + 4] for i in range(2, 26, 4))
    return " ".join(number[i:i + 4] for i in range(0, len(number), 4))
