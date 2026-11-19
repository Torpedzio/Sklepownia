"""Monitor messages: to the owner (push and e-mail, no technical cause) and to the staff (plain e-mail, full detail)."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import formats, timezone

from push.messages import Notice
from push.models import Topic

MINUTES = ("minutę", "minuty", "minut")
HOURS = ("godzinę", "godziny", "godzin")
DAYS = ("dzień", "dni", "dni")
# Keyed by Incident.repaired.
REPAIRS = {"start": "uruchomił kontener sklepu", "restart": "zrestartował kontener sklepu"}
REPAIR_FAILED = {
    "start": "Nie udało się uruchomić kontenera sklepu",
    "restart": "Nie udało się zrestartować kontenera sklepu",
}


def shop_down_notice(shop, since):
    return Notice(
        Topic.SHOPS,
        f"Sklep „{shop.name}” nie działa",
        f"Klienci nie mogą do niego wejść od {moment(since)}. Już to sprawdzamy i damy znać, gdy znowu zadziała.",
        f"/shops/{shop.pk}",
    )


def shop_back_notice(shop, since, until):
    return Notice(
        Topic.SHOPS,
        f"Sklep „{shop.name}” znowu działa",
        f"Nie działał przez {duration(until - since)}. Klienci znowu mogą kupować.",
        f"/shops/{shop.pk}",
    )


def shop_email(shop, reason, since, until=None):
    """`reason` is "down" or "back"."""
    if reason == "down":
        subject = f"Sklep „{shop.name}” nie działa"
        heading = "Sklep nie działa"
        intro = (
            f"Od {moment(since)} klienci nie mogą wejść do sklepu: nie odpowiada albo pokazuje błąd. "
            "Już to sprawdzamy. Nic nie musisz robić, a gdy sklep znowu zadziała, napiszemy."
        )
        rows = [("Sklep", shop.name), ("Adres", shop.url), ("Nie działa od", full_moment(since))]
    else:
        subject = f"Sklep „{shop.name}” znowu działa"
        heading = "Sklep znowu działa"
        intro = (
            f"Sklep nie działał przez {duration(until - since)}. Klienci znowu mogą do niego wchodzić i kupować."
        )
        rows = [
            ("Sklep", shop.name), ("Adres", shop.url),
            ("Przerwa", f"od {full_moment(since)} do {moment(until, since)}"),
        ]
    context = {
        "platform": settings.PLATFORM_NAME, "recipient": shop.owner.email, "heading": heading,
        "subheading": shop.name, "intro": intro, "rows": rows,
    }
    message = EmailMultiAlternatives(
        subject=subject, body=render_to_string("monitoring/email/shop.txt", context), to=[shop.owner.email],
    )
    message.attach_alternative(render_to_string("monitoring/email/shop.html", context), "text/html")
    return message


def shop_down_for_staff(shop, health, incident):
    repaired = REPAIRS.get(incident.repaired)
    return (
        f"Sklep {shop.slug} (nr {shop.pk}) nie działa",
        "\n".join([
            *_shop_lines(shop),
            f"Nie działa od: {full_moment(health.failing_since)}",
            f"Co widzi monitor: {health.problem}",
            f"Samonaprawa: {repaired}, nie pomogło." if repaired else "Samonaprawa: nie była możliwa.",
            "Właściciel dostał e-mail (i powiadomienie, jeśli ma aplikację w telefonie); napiszemy mu też, gdy sklep "
            "zadziała.",
            "",
            "Szczegóły: panel admina, Monitorowanie → Awarie i Stan sklepów. Logi: docker logs shop-"
            f"{shop.pk}, docker compose logs worker.",
        ]),
    )


def shop_back_for_staff(shop, since, until):
    return (
        f"Sklep {shop.slug} (nr {shop.pk}) znowu działa",
        "\n".join([
            *_shop_lines(shop),
            f"Nie działał przez {duration(until - since)}: od {full_moment(since)} do {moment(until, since)}.",
            "Właściciel dostał e-mail (i powiadomienie, jeśli ma aplikację w telefonie).",
        ]),
    )


def incident_for_staff(incident):
    return f"{incident.get_kind_display()}: {incident.summary}", "\n".join([
        incident.summary,
        f"Od: {full_moment(incident.started_at)}",
        "",
        "Napiszemy ponownie, gdy problem zniknie. Szczegóły: panel admina, Monitorowanie → Awarie.",
    ])


def solved_for_staff(incident):
    return f"Naprawione: {incident.summary}", "\n".join([
        incident.summary,
        f"Trwało {duration(incident.resolved_at - incident.started_at)}: od {full_moment(incident.started_at)} "
        f"do {moment(incident.resolved_at, incident.started_at)}.",
    ])


def _shop_lines(shop):
    return [
        f"Sklep: {shop.name} ({shop.get_platform_display()})",
        f"Adres: {shop.url}",
        f"Właściciel: {shop.owner.email}",
    ]


def duration(delta):
    """For use after "przez": "25 minut", "godzinę i 5 minut", "2 dni i 3 godziny"."""
    minutes = max(round(delta.total_seconds() / 60), 1)
    if minutes < 60:
        return _amount(minutes, MINUTES)
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return _amount(hours, HOURS) + (f" i {_amount(minutes, MINUTES)}" if minutes else "")
    days, hours = divmod(hours, 24)
    return _amount(days, DAYS) + (f" i {_amount(hours, HOURS)}" if hours else "")


def moment(value, today=None):
    """"10:42" on the same day as `today` (default now), else "18 listopada, 10:42"."""
    local = timezone.localtime(value)
    day = timezone.localtime(today or timezone.now()).date()
    time = formats.time_format(local, "H:i")
    return time if local.date() == day else f"{formats.date_format(local, 'j E')}, {time}"


def full_moment(value):
    """"19 listopada 2026, 10:42"."""
    return formats.date_format(timezone.localtime(value), "j E Y, H:i")


def plural(count, forms):
    one, few, many = forms
    if count == 1:
        return one
    return few if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else many


def _amount(count, forms):
    return forms[0] if count == 1 else f"{count} {plural(count, forms)}"
