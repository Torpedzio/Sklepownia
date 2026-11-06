"""E-mails about a shop sent to its owner. Admin passwords travel only this way, never through the API."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

# Why the e-mail goes out; each one says it in its own words.
REASONS = {
    "ready": {
        "subject": "Sklep „{name}” jest gotowy",
        "heading": "Twój sklep jest gotowy",
        "intro": "Sklep działa i klienci mogą już do niego wchodzić. Poniżej jest wszystko, czego potrzebujesz "
                 "na start: adres sklepu, jego ustawienia i dane do panelu, w którym dodasz produkty.",
    },
    "resend": {
        "subject": "Dane logowania do sklepu „{name}”",
        "heading": "Dane logowania do panelu sklepu",
        "intro": "Na prośbę z aplikacji wysyłamy ponownie dane do panelu Twojego sklepu.",
    },
    "new_password": {
        "subject": "Nowe hasło do panelu sklepu „{name}”",
        "heading": "Nowe hasło do panelu sklepu",
        "intro": "Hasło administratora zostało zmienione z aplikacji. Stare hasło już nie działa, "
                 "a wszyscy zalogowani do panelu zostali wylogowani.",
    },
}


def admin_access_message(shop, reason):
    """The e-mail with the shop's details and its WordPress admin login, ready to send."""
    texts = REASONS[reason]
    config = shop.config
    credentials = shop.credentials
    context = {
        **texts,
        "reason": reason,
        "platform": settings.PLATFORM_NAME,
        "shop": shop,
        "credentials": credentials,
        "recipient": shop.owner.email,
        "subheading": shop.name,
        "details": [
            ("Adres sklepu", shop.url),
            ("Branża", config.get_industry_display()),
            ("Motyw", config.template.name),
            ("Język", config.get_language_display()),
            ("Waluta", config.get_currency_display()),
            ("Kraj", config.get_country_display()),
            ("E-mail sklepu", config.contact_email),
        ],
    }
    message = EmailMultiAlternatives(
        subject=texts["subject"].format(name=shop.name),
        body=render_to_string("shops/email/admin_access.txt", context),
        to=[shop.owner.email],
    )
    message.attach_alternative(render_to_string("shops/email/admin_access.html", context), "text/html")
    return message
