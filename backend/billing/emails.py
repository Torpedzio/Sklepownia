"""E-mails about the owner's plan and payments."""

from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import formats, timezone

from .models import BillingProfile, Payment, Subscription


def _date(value):
    return formats.date_format(timezone.localtime(value), "j E Y") if value else ""


def _money(amount, currency):
    return f"{formats.number_format(amount, 2, force_grouping=True)} {currency}".replace("\xa0", " ")


def _payer(details):
    if details.get("kind") == BillingProfile.Kind.COMPANY:
        return f"{details.get('company_name')}, NIP {details.get('tax_id')}"
    return details.get("full_name", "")


def payment_message(kind, payment):
    plan = payment.plan
    subscription = payment.subscription
    rows = [
        ("Plan", plan.name),
        ("Kwota", _money(payment.amount, payment.currency)),
    ]
    if kind == "paid":
        rows.append(("Okres", f"{_date(payment.period_start)} – {_date(payment.period_end)}"))
    if subscription.card_tail:
        rows.append(("Karta", f"{subscription.card_brand} •••• {subscription.card_tail}".strip()))
    if payment.credit_used:
        rows.append(("Z salda", _money(payment.credit_used, payment.currency)))
    if payment.gateway_title:
        rows.append(("Numer płatności", payment.gateway_title))
    if payment.billing_details:
        rows.append(("Płacący", _payer(payment.billing_details)))

    if kind == "paid" and payment.kind == Payment.Kind.INITIAL:
        subject = f"Plan {plan.name} jest aktywny"
        heading = "Dziękujemy za płatność"
        intro = (f"Plan {plan.name} działa. Możesz zakładać sklepy, do {plan.max_shops} na raz. "
                 f"Następna płatność pobierze się sama z zapisanej karty {_date(payment.period_end)}.")
    elif kind == "paid":
        subject = f"Opłaciliśmy plan {plan.name} na kolejny okres"
        heading = "Plan przedłużony"
        intro = (f"Pobraliśmy opłatę z zapisanej karty. Plan działa do {_date(payment.period_end)}." if payment.amount
                 else f"Opłaciliśmy kolejny okres z salda nadpłaty. Plan działa do {_date(payment.period_end)}.")
    else:
        subject = f"Nie udało się pobrać opłaty za plan {plan.name}"
        heading = "Płatność się nie udała"
        intro = (f"Nie udało się pobrać opłaty z zapisanej karty. Spróbujemy ponownie "
                 f"{_date(subscription.next_attempt_at)}. Sprawdź, czy karta jest ważna i ma środki. "
                 "Do tego czasu sklepy działają, ale nowych nie założysz.")
    return _message(payment.user.email, subject, heading, intro, rows)


def plan_changed_message(subscription, old_plan, charged, credit_added, suspended, resumed):
    plan = subscription.plan
    rows = [("Poprzedni plan", old_plan), ("Nowy plan", plan.name), ("Sklepy w planie", str(plan.max_shops))]
    if Decimal(charged):
        rows.append(("Dopłata", _money(charged, plan.currency)))
    if Decimal(credit_added):
        rows.append(("Na saldo", _money(credit_added, plan.currency)))
    if suspended:
        rows.append(("Zawieszone sklepy", ", ".join(suspended)))
    if resumed:
        rows.append(("Przywrócone sklepy", ", ".join(resumed)))
    intro = f"Od teraz masz plan {plan.name}."
    if Decimal(credit_added):
        intro += " Niewykorzystaną część poprzedniego planu odliczymy od kolejnych płatności."
    if suspended:
        intro += (" Sklepy ponad limit planu są zawieszone: nie widzą ich klienci, ale nic z nich nie znika."
                  " Przywrócisz je w aplikacji po zmianie planu albo usunięciu innego sklepu.")
    if subscription.current_period_end:
        intro += (f" Następna płatność {_date(subscription.current_period_end)}: "
                  f"{_money(max(plan.price - subscription.credit, 0), plan.currency)}.")
    return _message(subscription.user.email, f"Zmieniliśmy plan na {plan.name}", "Plan zmieniony", intro, rows)


def ended_message(subscription):
    plan = subscription.plan
    if subscription.status == Subscription.Status.CANCELED:
        subject = f"Plan {plan.name} zakończył się"
        intro = "Plan został anulowany i nie będzie już odnawiany."
    else:
        subject = f"Plan {plan.name} wygasł"
        intro = "Nie udało się pobrać opłaty z zapisanej karty mimo kilku prób, więc plan wygasł."
    intro += " Nowych sklepów nie założysz, dopóki nie wybierzesz planu w aplikacji."
    return _message(subscription.user.email, subject, "Twój plan się zakończył", intro, [("Plan", plan.name)])


def _message(recipient, subject, heading, intro, rows):
    context = {
        "platform": settings.PLATFORM_NAME,
        "recipient": recipient,
        "heading": heading,
        "intro": intro,
        "rows": rows,
    }
    message = EmailMultiAlternatives(
        subject=subject, body=render_to_string("billing/email/notice.txt", context), to=[recipient],
    )
    message.attach_alternative(render_to_string("billing/email/notice.html", context), "text/html")
    return message
