"""Notification texts: the title says what happened, the body what to do; tapping opens `url` (an app route)."""

from dataclasses import dataclass

from django.utils import formats, timezone

from .models import Topic

PLURAL_NEW_ORDERS = ("nowe zamówienie", "nowe zamówienia", "nowych zamówień")


@dataclass(frozen=True)
class Notice:
    topic: str
    title: str
    body: str
    url: str


def new_orders(shop, orders):
    """`orders`: new `shops.orders.Order`s, newest last. Opens the order, or the list when there are several."""
    url = f"/shops/{shop.pk}/orders"
    if len(orders) == 1:
        order = orders[0]
        details = [f"Nr {order.number} na {money(order.total, order.currency)}", order.customer]
        return Notice(
            Topic.NEW_ORDERS, f"Nowe zamówienie: {shop.name}", ", ".join(filter(None, details)),
            f"{url}/{order.external_id}",
        )
    body = f"Najnowsze: nr {orders[-1].number}."
    currencies = {order.currency for order in orders}
    if len(currencies) == 1:
        body = f"Razem {money(sum(order.total for order in orders), currencies.pop())}. {body}"
    return Notice(Topic.NEW_ORDERS, f"{len(orders)} {_plural(len(orders), PLURAL_NEW_ORDERS)}: {shop.name}", body, url)


def shop_ready(shop):
    return Notice(
        Topic.SHOPS,
        f"Sklep „{shop.name}” jest gotowy",
        "Możesz dodawać produkty. Dane logowania do panelu wysłaliśmy e-mailem.",
        f"/shops/{shop.pk}",
    )


def shop_failed(shop):
    return Notice(
        Topic.SHOPS,
        f"Zakładanie sklepu „{shop.name}” zatrzymało się",
        "Otwórz sklep w aplikacji i spróbuj ponownie. Zaczniemy od kroku, który się nie udał.",
        f"/shops/{shop.pk}",
    )


def renewal_failed(plan, next_attempt_at):
    return Notice(
        Topic.BILLING,
        f"Nie udało się pobrać opłaty za plan {plan.name}",
        f"Spróbujemy ponownie {_day(next_attempt_at)}. Sprawdź, czy karta jest ważna i ma środki.",
        "/billing",
    )


def plan_ended(subscription):
    from billing.models import Subscription

    ended = "zakończył się" if subscription.status == Subscription.Status.CANCELED else "wygasł"
    return Notice(
        Topic.BILLING,
        f"Plan {subscription.plan.name} {ended}",
        "Nowych sklepów nie założysz, dopóki nie wybierzesz planu w aplikacji.",
        "/billing",
    )


def money(amount, currency):
    """'1 234,50 zł' for PLN, the code for other currencies."""
    number = formats.number_format(amount, 2, force_grouping=True).replace("\xa0", " ")
    return f"{number} {'zł' if currency == 'PLN' else currency}"


def _day(value):
    return formats.date_format(timezone.localtime(value), "j E")


def _plural(count, forms):
    one, few, many = forms
    if count == 1:
        return one
    return few if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else many
