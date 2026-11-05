from django.db import models


class Industry(models.TextChoices):
    FASHION = "fashion", "Odzież i moda"
    ELECTRONICS = "electronics", "Elektronika"
    HOME_GARDEN = "home_garden", "Dom i ogród"
    BEAUTY = "beauty", "Kosmetyki i uroda"
    FOOD = "food", "Żywność i napoje"
    SPORTS = "sports", "Sport i rekreacja"
    KIDS = "kids", "Dzieci i zabawki"
    BOOKS = "books", "Książki i multimedia"
    HANDMADE = "handmade", "Rękodzieło"
    AUTOMOTIVE = "automotive", "Motoryzacja"
    PETS = "pets", "Zwierzęta"
    OTHER = "other", "Inna"


class Language(models.TextChoices):
    # WordPress locale codes, used directly by `wp language core install`.
    PL = "pl_PL", "Polski"
    EN = "en_US", "English"
    DE = "de_DE", "Deutsch"


class Currency(models.TextChoices):
    PLN = "PLN", "Złoty (PLN)"
    EUR = "EUR", "Euro (EUR)"
    USD = "USD", "Dolar amerykański (USD)"
    GBP = "GBP", "Funt brytyjski (GBP)"


class Country(models.TextChoices):
    PL = "PL", "Polska"
    DE = "DE", "Niemcy"
    CZ = "CZ", "Czechy"
    SK = "SK", "Słowacja"
    GB = "GB", "Wielka Brytania"
    US = "US", "Stany Zjednoczone"


MIN_CATEGORY_COUNT = 1
MAX_CATEGORY_COUNT = 20


# Time zone a new shop gets from its country; also the time zones the settings offer.
COUNTRY_TIMEZONES = {
    "PL": "Europe/Warsaw",
    "DE": "Europe/Berlin",
    "CZ": "Europe/Prague",
    "SK": "Europe/Bratislava",
    "GB": "Europe/London",
    "US": "America/New_York",
}


class Timezone(models.TextChoices):
    WARSAW = "Europe/Warsaw", "Warszawa"
    BERLIN = "Europe/Berlin", "Berlin"
    PRAGUE = "Europe/Prague", "Praga"
    BRATISLAVA = "Europe/Bratislava", "Bratysława"
    LONDON = "Europe/London", "Londyn"
    NEW_YORK = "America/New_York", "Nowy Jork"
    CHICAGO = "America/Chicago", "Chicago"
    LOS_ANGELES = "America/Los_Angeles", "Los Angeles"
    UTC = "UTC", "UTC"


# Common VAT rates per country, standard rate first. The settings accept any rate; these are suggestions.
VAT_RATES = {
    "PL": ["23.00", "8.00", "5.00", "0.00"],
    "DE": ["19.00", "7.00", "0.00"],
    "CZ": ["21.00", "12.00", "0.00"],
    "SK": ["23.00", "19.00", "5.00", "0.00"],
    "GB": ["20.00", "5.00", "0.00"],
    "US": ["0.00"],
}
