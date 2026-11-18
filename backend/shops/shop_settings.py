"""
Shop settings the owner can change in the app, grouped in sections as the app shows them.

The section serializers below are the schema: they validate input, give every field its label
(shown in the change history) and turn values into plain JSON (money as "15.00").
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from billing.validators import normalize_nip, validate_nip, validate_polish_postal_code

from .choices import COUNTRY_TIMEZONES, VAT_RATES, Country, Currency, Language, Timezone
from .models import ShopTemplate

MONEY = {"max_digits": 10, "decimal_places": 2, "min_value": Decimal("0")}
# Stands for a key in the change history (ShopOperation.changes); the key itself never leaves the operation.
SECRET_PLACEHOLDER = "••••••••"


class SecretField(serializers.CharField):
    """
    A key the app only writes: it goes to the shop, and the platform neither stores nor shows it (see split_secrets).
    Left blank, the shop keeps the key it has.
    """

    def __init__(self, **kwargs):
        super().__init__(write_only=True, required=False, allow_blank=True, **kwargs)


def _digits(value, label):
    value = re.sub(r"\s", "", value)
    if value and not re.fullmatch(r"\d+", value):
        raise serializers.ValidationError(f"{label} składa się z samych cyfr.")
    return value


def _hex_key(value, length):
    value = re.sub(r"\s", "", value).lower()
    if value and not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        # 16 znaków, 32 znaki.
        chars = "znaki" if length % 10 in (2, 3, 4) and length % 100 not in (12, 13, 14) else "znaków"
        raise serializers.ValidationError(f"Klucz ma {length} {chars}: cyfry i litery od a do f.")
    return value


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
    # Online payments: the operator's plugin is installed in the shop the first time it's turned on.
    przelewy24_enabled = serializers.BooleanField(label="Płatności Przelewy24")
    przelewy24_sandbox = serializers.BooleanField(label="Tryb testowy Przelewy24")
    przelewy24_merchant_id = serializers.CharField(label="ID sprzedawcy Przelewy24", max_length=15, allow_blank=True)
    przelewy24_crc_key = SecretField(label="Klucz CRC Przelewy24")
    przelewy24_api_key = SecretField(label="Klucz API Przelewy24")
    przelewy24_keys_saved = serializers.BooleanField(
        label="Klucze Przelewy24 w sklepie", read_only=True,
        help_text="Sklep ma klucz CRC i klucz API do wybranego trybu (testowego albo produkcyjnego).",
    )
    payu_enabled = serializers.BooleanField(label="Płatności PayU")
    payu_sandbox = serializers.BooleanField(label="Tryb testowy PayU")
    payu_pos_id = serializers.CharField(label="Id punktu płatności PayU", max_length=15, allow_blank=True)
    payu_client_id = serializers.CharField(label="OAuth client_id PayU", max_length=15, allow_blank=True)
    payu_md5_key = SecretField(label="Drugi klucz MD5 PayU")
    payu_client_secret = SecretField(label="OAuth client_secret PayU")
    payu_keys_saved = serializers.BooleanField(
        label="Klucze PayU w sklepie", read_only=True,
        help_text="Sklep ma drugi klucz MD5 i client_secret do wybranego trybu (testowego albo produkcyjnego).",
    )

    def validate_przelewy24_merchant_id(self, value):
        return _digits(value, "ID sprzedawcy")

    def validate_przelewy24_crc_key(self, value):
        return _hex_key(value, 16)

    def validate_przelewy24_api_key(self, value):
        return _hex_key(value, 32)

    def validate_payu_pos_id(self, value):
        return _digits(value, "Id punktu płatności")

    def validate_payu_client_id(self, value):
        return _digits(value, "client_id")

    def validate_payu_md5_key(self, value):
        return _hex_key(value, 32)

    def validate_payu_client_secret(self, value):
        return _hex_key(value, 32)

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


class SellerRegister(serializers.ChoiceField):
    CHOICES = (
        ("ceidg", "Działalność gospodarcza (CEIDG)"),
        ("krs", "Spółka w KRS"),
        ("unregistered", "Działalność nierejestrowana"),
    )

    def __init__(self, **kwargs):
        super().__init__(choices=self.CHOICES, **kwargs)


class DocumentsSection(serializers.Serializer):
    """
    The shop's terms of sale and privacy policy, written from our templates (shops/documents.py) and published as
    pages in the shop. The platform keeps the seller's details; the shop gets the finished documents.
    """

    managed = serializers.BooleanField(label="Regulamin i polityka prywatności z aplikacji")
    seller_name = serializers.CharField(label="Nazwa sprzedawcy", max_length=200, allow_blank=True)
    register = SellerRegister(label="Forma działalności")
    street = serializers.CharField(label="Ulica sprzedawcy", max_length=200, allow_blank=True)
    postal_code = serializers.CharField(label="Kod pocztowy sprzedawcy", max_length=6, allow_blank=True)
    city = serializers.CharField(label="Miejscowość sprzedawcy", max_length=100, allow_blank=True)
    tax_id = serializers.CharField(label="NIP sprzedawcy", max_length=20, allow_blank=True)
    regon = serializers.CharField(label="REGON sprzedawcy", max_length=20, allow_blank=True)
    krs = serializers.CharField(label="Numer KRS sprzedawcy", max_length=20, allow_blank=True)
    phone = serializers.CharField(label="Telefon w dokumentach", max_length=30, allow_blank=True)
    return_days = serializers.IntegerField(label="Dni na odstąpienie od umowy", min_value=14, max_value=365)
    free_returns = serializers.BooleanField(label="Darmowy zwrot")
    dispatch_days = serializers.IntegerField(label="Czas wysyłki", min_value=1, max_value=30)
    # Where the documents are in the shop and which version of our templates they follow, after publishing.
    terms_url = serializers.CharField(read_only=True)
    privacy_url = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)

    def validate_seller_name(self, value):
        return " ".join(value.split())

    def validate_postal_code(self, value):
        value = value.strip()
        if value:
            _django_check(validate_polish_postal_code, value)
        return value

    def validate_tax_id(self, value):
        if not value.strip():
            return ""
        _django_check(validate_nip, value)
        return normalize_nip(value)

    def validate_regon(self, value):
        value = _digits(value, "REGON")
        if value and len(value) not in (9, 14):
            raise serializers.ValidationError("REGON ma 9 albo 14 cyfr.")
        return value

    def validate_krs(self, value):
        value = _digits(value, "Numer KRS")
        if value and len(value) != 10:
            raise serializers.ValidationError("Numer KRS ma 10 cyfr, np. 0000123456.")
        return value

    def validate_phone(self, value):
        value = " ".join(value.split())
        if value and not re.fullmatch(r"\+?[\d ()-]{7,}", value):
            raise serializers.ValidationError("Wpisz numer telefonu, np. 600 100 200.")
        return value


def _django_check(validator, value):
    try:
        validator(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc


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
    "documents": DocumentsSection,
}

FIELD_LABELS = {
    section: {name: str(field.label) for name, field in serializer().fields.items()}
    for section, serializer in SECTIONS.items()
}

# Keys the app writes to the shop but never keeps: {section: (field, …)}.
SECRET_FIELDS = {
    section: tuple(name for name, field in serializer().fields.items() if isinstance(field, SecretField))
    for section, serializer in SECTIONS.items()
}


@dataclass(frozen=True)
class Operator:
    """An online payment operator, as the payments section has it: fields named <key>_…"""

    key: str
    name: str
    # What identifies the owner's account, kept in the settings.
    ids: tuple
    # What signs the payments: written to the shop, never kept (SecretField).
    keys: tuple


OPERATORS = {
    "przelewy24": Operator(
        "przelewy24", "Przelewy24", ids=("przelewy24_merchant_id",), keys=("przelewy24_crc_key", "przelewy24_api_key"),
    ),
    "payu": Operator(
        "payu", "PayU", ids=("payu_pos_id", "payu_client_id"), keys=("payu_md5_key", "payu_client_secret"),
    ),
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
            **_operator_defaults(),
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
        "documents": {
            "managed": False,
            "register": "ceidg",
            **_seller_defaults(shop.owner),
            "regon": "",
            "krs": "",
            "phone": "",
            "return_days": 14,
            "free_returns": False,
            "dispatch_days": 2,
            "terms_url": "",
            "privacy_url": "",
            "version": "",
        },
    }


def _seller_defaults(owner):
    """The seller's details as the owner gave them for our invoices, a start for the documents."""
    profile = getattr(owner, "billing_profile", None) if owner else None
    if profile is None:
        return {"seller_name": "", "street": "", "postal_code": "", "city": "", "tax_id": ""}
    company = profile.kind == profile.Kind.COMPANY
    return {
        "seller_name": profile.company_name if company else profile.full_name,
        "street": profile.street,
        "postal_code": profile.postal_code,
        "city": profile.city,
        "tax_id": normalize_nip(profile.tax_id) if company and profile.country == Country.PL else "",
    }


def _operator_defaults():
    """Every operator off, without an account, in production mode."""
    values = {}
    for key, operator in OPERATORS.items():
        values.update({f"{key}_enabled": False, f"{key}_sandbox": False, f"{key}_keys_saved": False})
        values.update({field: "" for field in operator.ids})
    return values


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
        # Online payment operators the platform can set up (context["operators"]).
        operators = self.context.get("operators", tuple(OPERATORS))
        given = attrs.get("payments", {})
        for key, operator in OPERATORS.items():
            if key not in operators and any(field.startswith(f"{key}_") for field in given):
                errors.setdefault("payments", {})[f"{key}_enabled"] = [
                    f"Płatności {operator.name} włączysz w panelu sklepu.",
                ]
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
        missing = _operator_errors(self.context["current"]["payments"], payments, attrs.get("payments", {}))
        if missing:
            errors["payments"] = {**errors.get("payments", {}), **missing}
        for section, fields in _documents_errors(merged, attrs).items():
            errors[section] = {**errors.get(section, {}), **fields}
        shopping = merged["shopping"]
        if not shopping["guest_checkout"] and not shopping["signup_at_checkout"]:
            errors["shopping"] = {
                "guest_checkout": ["Klienci muszą móc kupić bez konta albo założyć je przy zamówieniu."],
            }
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def _documents_errors(values, given):
    """What the documents miss, when they are on and their details or the shop's country are being changed."""
    if not values["documents"]["managed"]:
        return {}
    if "documents" in given:
        return documents_errors(values)
    if "country" in given.get("region", {}) and values["region"]["country"] != Country.PL:
        return {"region": {"country": [
            "Regulamin z aplikacji jest dla sklepów sprzedających z Polski. Najpierw wyłącz go w sekcji Regulamin.",
        ]}}
    return {}


def documents_errors(values):
    """{section: {field: [message]}} of what the documents need and don't have; also for a preview."""
    documents = values["documents"]
    required = ["seller_name", "street", "postal_code", "city"]
    if documents["register"] in ("ceidg", "krs"):
        required.append("tax_id")
    if documents["register"] == "krs":
        required.append("krs")
    errors = {field: ["Potrzebne do regulaminu."] for field in required if not documents[field]}
    if values["region"]["country"] != Country.PL:
        errors["managed"] = ["Wzory regulaminu i polityki prywatności są na razie dla sklepów sprzedających z Polski."]
    return {"documents": errors} if errors else {}


def _operator_errors(current, payments, given):
    """
    What's missing for the operators being changed (`given` has their fields) that will be on:
    their ids, and their keys unless the shop has them.
    """
    errors = {}
    for key, operator in OPERATORS.items():
        if not payments[f"{key}_enabled"] or not any(field.startswith(f"{key}_") for field in given):
            continue
        for field in operator.ids:
            if not payments[field]:
                errors[field] = [f"Wpisz z panelu {operator.name}."]
        # Test and production accounts have different keys, so a new mode needs them again.
        mode_changed = payments[f"{key}_sandbox"] != current[f"{key}_sandbox"]
        if mode_changed or not payments[f"{key}_keys_saved"]:
            message = (
                "Klucze testowe i produkcyjne są różne. Wpisz klucz do nowego trybu."
                if mode_changed and payments[f"{key}_keys_saved"]
                else f"Wpisz z panelu {operator.name}."
            )
            for field in operator.keys:
                if not payments.get(field):
                    errors[field] = [message]
    return errors


def split_secrets(changes):
    """
    `changes` (normalized input) without the keys, and the keys given, both {section: {field: value}}.
    A key left blank isn't a change: the shop keeps the one it has.
    """
    rest, keys = {}, {}
    for section, fields in changes.items():
        secret = SECRET_FIELDS.get(section, ())
        rest[section] = {name: value for name, value in fields.items() if name not in secret}
        given = {name: value for name, value in fields.items() if name in secret and value}
        if given:
            keys[section] = given
    return {section: fields for section, fields in rest.items() if fields}, keys


def with_placeholders(changes, keys):
    """`changes` with SECRET_PLACEHOLDER for every key given, so the history says a key was changed."""
    result = {section: dict(fields) for section, fields in changes.items()}
    for section, fields in keys.items():
        result.setdefault(section, {}).update({name: SECRET_PLACEHOLDER for name in fields})
    return result


def reveal(changes, keys):
    """`changes` of an operation with its keys in place of the placeholders: what the shop gets."""
    result = {section: dict(fields) for section, fields in changes.items()}
    for section, fields in keys.items():
        result.setdefault(section, {}).update(fields)
    return result


def conceal(values, keys):
    """
    `values` (settings after a change) as the platform keeps them: without keys, and with every operator
    whose keys were just written marked as having them.
    """
    result = {section: dict(fields) for section, fields in values.items()}
    for section, fields in result.items():
        for name in SECRET_FIELDS.get(section, ()):
            fields.pop(name, None)
    given = keys.get("payments", {})
    for key, operator in OPERATORS.items():
        if any(name in given for name in operator.keys) and "payments" in result:
            result["payments"][f"{key}_keys_saved"] = True
    return result


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
