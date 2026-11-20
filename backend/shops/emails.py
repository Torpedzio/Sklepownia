"""E-mails about a shop. Admin passwords travel only this way (to the owner), never through the API."""

from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .platforms import platform_info

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


# (section, name) in the order the e-mail lists them; sections the platform's app lacks go to "in the panel".
FIRST_SETTINGS = (("payments", "płatności"), ("shipping", "wysyłkę"), ("taxes", "podatki"), ("documents", "regulamin"))


def admin_access_message(shop, reason):
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
        "settings_note": settings_note(shop.platform),
        "details": [
            ("Adres sklepu", shop.url),
            ("Platforma", shop.get_platform_display()),
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


def settings_note(platform):
    sections = platform_info(platform).settings_sections
    in_app = [name for section, name in FIRST_SETTINGS if section in sections]
    in_panel = [name for section, name in FIRST_SETTINGS if section not in sections]
    note = f"{_listed(in_app)} ustawisz w aplikacji, w ustawieniach sklepu." if in_app else ""
    if in_panel:
        note += f" {_listed(in_panel)} w panelu sklepu." if note else f"{_listed(in_panel)} ustawisz w panelu sklepu."
    return note


def _listed(names):
    """E.g. "Płatności, wysyłkę i podatki"."""
    text = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} i {names[-1]}"
    return text[0].upper() + text[1:]


def invitation_message(invitation):
    """Leads to signing in, or signing up when the address has no account; the app shows the invitation there."""
    from accounts.models import User

    shop, inviter = invitation.shop, invitation.invited_by
    name = (inviter.get_full_name() or inviter.email) if inviter else "Właściciel sklepu"
    has_account = User.objects.filter(email=invitation.email, is_active=True).exists()
    path = "/sign-in" if has_account else "/sign-up"
    context = {
        "platform": settings.PLATFORM_NAME,
        "recipient": invitation.email,
        "heading": "Zaproszenie do obsługi sklepu",
        "subheading": shop.name,
        "intro": f"{name} zaprasza Cię do zespołu sklepu „{shop.name}”. W aplikacji zobaczysz sklep i jego sprzedaż.",
        "action": "Zaloguj się na to konto, a zaproszenie pojawi się na liście sklepów."
        if has_account else "Załóż konto na ten adres, a po potwierdzeniu e-maila zaproszenie pojawi się na liście sklepów.",
        "url": f"{settings.APP_URL}{path}?{urlencode({'email': invitation.email})}",
        "label": "Zaloguj się" if has_account else "Załóż konto",
        "shop_url": shop.url,
        "expires_at": invitation.expires_at,
    }
    message = EmailMultiAlternatives(
        subject=f"Zaproszenie do sklepu „{shop.name}”",
        body=render_to_string("shops/email/invitation.txt", context),
        to=[invitation.email],
    )
    message.attach_alternative(render_to_string("shops/email/invitation.html", context), "text/html")
    return message
