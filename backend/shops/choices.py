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
