import re

from django.core.exceptions import ValidationError

NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)


def normalize_nip(value):
    """A Polish tax ID as 10 digits; "PL 123-456-78-19" becomes "1234567819"."""
    return re.sub(r"[\s-]", "", value or "").upper().removeprefix("PL")


def validate_nip(value):
    nip = normalize_nip(value)
    if not re.fullmatch(r"\d{10}", nip):
        raise ValidationError("NIP ma 10 cyfr.")
    checksum = sum(int(digit) * weight for digit, weight in zip(nip, NIP_WEIGHTS)) % 11
    if checksum == 10 or checksum != int(nip[9]):
        raise ValidationError("Ten NIP ma błąd. Sprawdź, czy nie brakuje cyfry.")


def validate_polish_postal_code(value):
    if not re.fullmatch(r"\d{2}-\d{3}", value or ""):
        raise ValidationError("Kod pocztowy w formacie 00-000.")
