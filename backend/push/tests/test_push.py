import json
import urllib.error
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing import services as billing
from billing.models import Subscription
from conftest import subscribe
from push import services
from push.models import PushDevice, PushPreferences, PushTicket
from push.senders.base import Message, PushError, PushUnavailable
from push.senders.expo import ExpoSender
from push.senders.memory import MemorySender
from shops import sales
from shops.models import Shop
from shops.orders import Order

pytestmark = pytest.mark.django_db

TOKEN = "ExponentPushToken[abc123]"
OTHER_TOKEN = "ExpoPushToken[xyz-789]"
READ_ORDERS = "shops.provisioning.fake.FakeProvisioner.read_orders"


def phone(user, token=TOKEN, platform="android"):
    return PushDevice.objects.create(user=user, token=token, platform=platform, name="Pixel 8")


# --- the phone and the choices ---


def test_the_app_registers_the_phone_once(auth_client, verified_user):
    payload = {"token": TOKEN, "platform": "ios", "name": "iPhone 15"}

    first = auth_client.post("/api/push/devices/", payload, format="json")
    again = auth_client.post("/api/push/devices/", payload, format="json")

    assert (first.status_code, again.status_code) == (201, 200)
    assert list(PushDevice.objects.values_list("user", "platform", "name")) == [(verified_user.pk, "ios", "iPhone 15")]


def test_a_phone_signed_in_to_another_account_moves_to_it(auth_client, verified_user):
    other = User.objects.create_user(email="inny@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    phone(other)

    auth_client.post("/api/push/devices/", {"token": TOKEN, "platform": "android"}, format="json")

    assert PushDevice.objects.get(token=TOKEN).user == verified_user


def test_only_expo_tokens_from_verified_accounts_are_taken(auth_client, api_client):
    bad = auth_client.post("/api/push/devices/", {"token": "abc", "platform": "android"}, format="json")
    unverified = User.objects.create_user(email="nowy@example.com", password="Sekretne-haslo-123")
    api_client.force_authenticate(unverified)

    assert bad.status_code == 400 and "token" in bad.data
    assert api_client.post("/api/push/devices/", {"token": TOKEN, "platform": "ios"}).status_code == 403


def test_signing_out_forgets_only_ones_own_phone(auth_client, verified_user):
    other = User.objects.create_user(email="inny@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    phone(other, OTHER_TOKEN)
    phone(verified_user)

    for token in (TOKEN, OTHER_TOKEN):
        assert auth_client.post("/api/push/devices/forget/", {"token": token}).status_code == 204

    assert list(PushDevice.objects.values_list("token", flat=True)) == [OTHER_TOKEN]


def test_the_owner_chooses_what_the_notifications_are_about(auth_client, verified_user):
    phone(verified_user)

    data = auth_client.get("/api/push/preferences/").data
    changed = auth_client.patch("/api/push/preferences/", {"new_orders": False}, format="json").data

    assert (data["new_orders"], data["shops"], data["billing"]) == (True, True, True)
    assert [(d["name"], d["platform_display"]) for d in data["devices"]] == [("Pixel 8", "Android")]
    assert (changed["new_orders"], changed["shops"]) == (False, True)
    assert "token" not in data["devices"][0]


# --- new orders ---


def placed(days_ago):
    return timezone.make_aware(datetime.combine(timezone.localdate() - timedelta(days=days_ago), time(8)))


def order(number, days_ago=0, status="processing", total="49.90", customer="Anna N."):
    at = placed(days_ago)
    return Order(external_id=str(number), number=str(number), status=status, total=Decimal(total), currency="PLN",
                 items=1, customer=customer, placed_at=at, changed_at=timezone.now())


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Palarnia", "slug": "palarnia", "industry": "food", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    return Shop.objects.get(pk=shop_id)


@pytest.fixture
def shop_orders(monkeypatch):
    orders = []
    monkeypatch.setattr(READ_ORDERS, lambda provisioner, shop, since, limit: list(orders))
    return orders


def sync(shop, captured):
    with captured(execute=True):
        sales.sync(shop.pk)


def test_a_new_order_is_announced(shop, shop_orders, push_outbox, django_capture_on_commit_callbacks):
    phone(shop.owner)
    shop_orders.append(order(1, days_ago=3))
    sync(shop, django_capture_on_commit_callbacks)
    # What the shop had before the first read is not news.
    assert push_outbox == []

    shop_orders.append(order(2, total="1234.5"))
    sync(shop, django_capture_on_commit_callbacks)

    assert push_outbox == [Message(token=TOKEN, title="Nowe zamówienie: Palarnia", body="Nr 2 na 1 234,50 zł, Anna N.",
                                   url=f"/shops/{shop.pk}/sales", topic="new_orders")]


def test_several_new_orders_come_as_one_notification(shop, shop_orders, push_outbox,
                                                      django_capture_on_commit_callbacks):
    phone(shop.owner)
    sync(shop, django_capture_on_commit_callbacks)
    shop_orders.extend([order(5, total="10.00"), order(6, total="20.00"), order(7, status="new", total="30.00")])

    sync(shop, django_capture_on_commit_callbacks)

    (message,) = push_outbox
    assert (message.title, message.body) == ("3 nowe zamówienia: Palarnia", "Razem 60,00 zł. Najnowsze: nr 7.")


def test_an_order_is_announced_once_it_is_paid(shop, shop_orders, push_outbox, django_capture_on_commit_callbacks):
    phone(shop.owner)
    sync(shop, django_capture_on_commit_callbacks)
    shop_orders.append(order(3, status="unfinished"))
    sync(shop, django_capture_on_commit_callbacks)
    assert push_outbox == []

    shop_orders[0] = order(3, status="processing")
    sync(shop, django_capture_on_commit_callbacks)
    sync(shop, django_capture_on_commit_callbacks)

    assert [message.title for message in push_outbox] == ["Nowe zamówienie: Palarnia"]


def test_old_or_cancelled_orders_and_unwanted_news_stay_quiet(shop, shop_orders, push_outbox,
                                                             django_capture_on_commit_callbacks):
    phone(shop.owner)
    sync(shop, django_capture_on_commit_callbacks)
    shop_orders.extend([order(8, days_ago=10), order(9, status="cancelled")])
    sync(shop, django_capture_on_commit_callbacks)
    assert push_outbox == []

    PushPreferences.objects.create(user=shop.owner, new_orders=False)
    shop_orders.append(order(10))
    sync(shop, django_capture_on_commit_callbacks)
    assert push_outbox == []


# --- shops and the plan ---


def test_the_end_of_setup_is_announced(verified_user, auth_client, push_outbox, settings,
                                       django_capture_on_commit_callbacks):
    phone(verified_user)
    payload = {"name": "Palarnia", "slug": "palarnia", "industry": "food", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        ready = auth_client.post("/api/shops/", payload, format="json").data["id"]
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "install_theme"
    with django_capture_on_commit_callbacks(execute=True):
        failed = auth_client.post("/api/shops/", {**payload, "slug": "druga"}, format="json").data["id"]

    assert [(m.title, m.url, m.topic) for m in push_outbox] == [
        ("Sklep „Palarnia” jest gotowy", f"/shops/{ready}", "shops"),
        ("Zakładanie sklepu „Palarnia” zatrzymało się", f"/shops/{failed}", "shops"),
    ]


def test_a_failed_renewal_and_the_end_of_the_plan_are_announced(user, plan, push_outbox, settings,
                                                                django_capture_on_commit_callbacks):
    settings.FAKE_GATEWAY_DECLINE_RENEWALS = True
    phone(user)
    subscribe(user, plan, current_period_end=timezone.now() - timedelta(minutes=1))

    with django_capture_on_commit_callbacks(execute=True):
        billing.renew_due()
    for _ in range(3):
        Subscription.objects.filter(user=user).update(next_attempt_at=timezone.now())
        with django_capture_on_commit_callbacks(execute=True):
            billing.renew_due()

    titles = [message.title for message in push_outbox]
    assert titles == ["Nie udało się pobrać opłaty za plan Standard"] * 3 + ["Plan Standard wygasł"]
    assert push_outbox[0].body.startswith("Spróbujemy ponownie ") and push_outbox[0].url == "/billing"


# --- delivery ---


def test_each_phone_of_the_owner_gets_it_unless_it_has_no_app_any_more(user, push_outbox):
    phone(user, TOKEN)
    phone(user, OTHER_TOKEN, "ios")
    MemorySender.unregistered.add(OTHER_TOKEN)

    assert services.send(user.pk, "shops", "Tytuł", "Treść", "/shops") == 1

    assert [message.token for message in push_outbox] == [TOKEN]
    assert list(PushDevice.objects.values_list("token", flat=True)) == [TOKEN]
    assert PushTicket.objects.count() == 1


def test_receipts_drop_phones_that_no_longer_take_notifications(user, push_outbox):
    kept, gone = phone(user, TOKEN), phone(user, OTHER_TOKEN)
    MemorySender.unregistered_later.add(OTHER_TOKEN)
    services.send(user.pk, "shops", "Tytuł", "Treść", "/shops")

    services.check_receipts()
    assert PushTicket.objects.count() == 2

    services.check_receipts(now=timezone.now() + services.RECEIPT_AFTER + timedelta(seconds=1))

    assert list(PushDevice.objects.all()) == [kept]
    assert not PushTicket.objects.exists()
    assert not PushDevice.objects.filter(pk=gone.pk).exists()


def test_receipts_that_never_come_are_forgotten_after_a_day(user, push_outbox):
    device = phone(user)
    PushTicket.objects.create(device=device, ticket_id="lost")

    services.check_receipts(now=timezone.now() + timedelta(days=1, minutes=1))

    assert not PushTicket.objects.exists()
    assert PushDevice.objects.filter(pk=device.pk).exists()


def test_nothing_is_queued_for_an_owner_without_phones(user, push_outbox, django_capture_on_commit_callbacks):
    from push.messages import Notice

    with django_capture_on_commit_callbacks() as callbacks:
        services.notify(user.pk, Notice("shops", "Tytuł", "Treść", "/shops"))

    assert callbacks == []


def test_signing_out_everywhere_and_deleting_the_account_forget_the_phones(api_client, verified_user):
    api_client.force_authenticate(verified_user)
    phone(verified_user)
    assert api_client.post("/api/auth/logout-everywhere/").status_code == 205
    assert not PushDevice.objects.exists()

    phone(verified_user)
    PushPreferences.objects.create(user=verified_user)
    api_client.post("/api/auth/delete-account/", {"password": "Sekretne-haslo-123"}, format="json")

    assert not PushDevice.objects.exists() and not PushPreferences.objects.exists()


# --- Expo's push service ---


def expo_answer(body):
    response = mock.MagicMock()
    response.read.return_value = json.dumps(body).encode()
    response.__enter__.return_value = response
    return response


def test_expo_gets_the_message_with_its_screen_and_channel(settings):
    settings.EXPO_ACCESS_TOKEN = "secret"
    message = Message(token=TOKEN, title="Tytuł", body="Treść", url="/shops/7/sales", topic="new_orders")
    answer = {"data": [{"status": "ok", "id": "r-1"},
                       {"status": "error", "message": "gone", "details": {"error": "DeviceNotRegistered"}}]}

    with mock.patch("urllib.request.urlopen", return_value=expo_answer(answer)) as urlopen:
        tickets = ExpoSender().send([message, message])

    request = urlopen.call_args.args[0]
    assert request.full_url == "https://exp.host/--/api/v2/push/send"
    assert request.get_header("Authorization") == "Bearer secret"
    assert json.loads(request.data)[0] == {
        "to": TOKEN, "title": "Tytuł", "body": "Treść", "data": {"url": "/shops/7/sales"}, "sound": "default",
        "priority": "high", "channelId": "new_orders",
    }
    assert [(t.ok, t.id, t.error) for t in tickets] == [(True, "r-1", ""), (False, "", "DeviceNotRegistered")]


def test_expo_receipts_and_errors():
    answer = {"data": {"r-1": {"status": "ok"}, "r-2": {"status": "error", "details": {"error": "MessageTooBig"}}}}
    with mock.patch("urllib.request.urlopen", return_value=expo_answer(answer)):
        receipts = ExpoSender().receipts(["r-1", "r-2", "r-3"])
    assert {key: (r.ok, r.error) for key, r in receipts.items()} == {"r-1": (True, ""), "r-2": (False, "MessageTooBig")}

    def refuse(code):
        return urllib.error.HTTPError("https://exp.host", code, "x", {}, BytesIO(b'{"errors": []}'))

    message = Message(token=TOKEN, title="T", body="B", url="/", topic="shops")
    with mock.patch("urllib.request.urlopen", side_effect=refuse(429)), pytest.raises(PushUnavailable):
        ExpoSender().send([message])
    with mock.patch("urllib.request.urlopen", side_effect=refuse(400)), pytest.raises(PushError) as error:
        ExpoSender().send([message])
    assert not isinstance(error.value, PushUnavailable)
