"""Changing plans: Standard (49 zł, 3 shops) halfway through its period, unless a test says otherwise."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from billing import services
from billing.models import Payment, Plan, Subscription
from conftest import subscribe
from shops.models import ProvisioningJob, Shop, ShopConfig, ShopTemplate

pytestmark = pytest.mark.django_db

RETURN_URL = "http://localhost:8081/billing/return"


@pytest.fixture
def plans(plan):
    return {code: Plan.objects.get(code=code) for code in ("start", "standard", "business")}


@pytest.fixture
def halfway(verified_user):
    now = timezone.now()
    Subscription.objects.filter(user=verified_user).update(
        current_period_start=now - timedelta(days=15), current_period_end=now + timedelta(days=15),
    )
    return Subscription.objects.get(user=verified_user)


def make_shops(user, *names, status=Shop.Status.ACTIVE, finished=True):
    shops = []
    for index, name in enumerate(names):
        shop = Shop.objects.create(owner=user, name=name, slug=name.lower(), status=status)
        Shop.objects.filter(pk=shop.pk).update(created_at=timezone.now() - timedelta(days=30 - index))
        ShopConfig.objects.create(shop=shop, industry="food", template=ShopTemplate.objects.get(slug="storefront"),
                                  category_count=3, contact_email="kontakt@example.com")
        ProvisioningJob.objects.create(
            shop=shop, status=ProvisioningJob.Status.SUCCEEDED if finished else ProvisioningJob.Status.FAILED,
        )
        shops.append(shop)
    return shops


@pytest.fixture
def client(auth_client):
    return auth_client


def preview(client, plan, **data):
    return client.post("/api/billing/subscription/change-preview/", {"plan": plan, **data}, format="json")


def change(client, captured, plan, **data):
    with captured(execute=True):
        return client.post("/api/billing/subscription/change/",
                           {"plan": plan, "return_url": RETURN_URL, **data}, format="json")


# --- dearer plan ---


def test_upgrading_costs_the_difference_for_the_rest_of_the_period(client, halfway, plans):
    data = preview(client, "business").data

    assert data["direction"] == "upgrade"
    assert (data["surcharge"], data["amount_due"], data["waived"]) == ("25.00", "25.00", False)
    assert data["blocked"] == ""


def test_upgrade_waits_for_the_surcharge_then_keeps_the_billing_date(
    client, halfway, plans, django_capture_on_commit_callbacks, mailoutbox,
):
    response = change(client, django_capture_on_commit_callbacks, "business")

    assert response.status_code == 201
    payment = Payment.objects.get(pk=response.data["payment"]["id"])
    assert (payment.kind, payment.amount, payment.plan.code) == (Payment.Kind.UPGRADE, Decimal("25.00"), "business")
    assert payment.return_url == f"{RETURN_URL}?payment={payment.pk}"
    assert Subscription.objects.get(pk=halfway.pk).plan.code == "standard"

    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"/api/billing/fake-gateway/{payment.pk}/", {"action": "pay"})

    subscription = Subscription.objects.get(pk=halfway.pk)
    assert subscription.plan.code == "business"
    assert subscription.current_period_end == halfway.current_period_end
    assert mailoutbox[-1].subject == "Zmieniliśmy plan na Biznes"
    assert "25,00 PLN" in mailoutbox[-1].body
    assert client.get("/api/auth/me/").data["shop_limit"] == 10


def test_a_declined_surcharge_changes_nothing(client, halfway, plans, django_capture_on_commit_callbacks):
    payment_id = change(client, django_capture_on_commit_callbacks, "business").data["payment"]["id"]

    client.post(f"/api/billing/fake-gateway/{payment_id}/", {"action": "decline"})

    assert Subscription.objects.get(pk=halfway.pk).plan.code == "standard"
    # Another try is allowed once the declined payment is settled.
    assert preview(client, "business").data["blocked"] == ""


def test_a_surcharge_below_5_zl_is_not_charged(client, verified_user, plans, django_capture_on_commit_callbacks):
    now = timezone.now()
    Subscription.objects.filter(user=verified_user).update(
        current_period_start=now - timedelta(days=29), current_period_end=now + timedelta(days=1),
    )

    response = change(client, django_capture_on_commit_callbacks, "business")

    assert response.status_code == 200
    assert response.data["change"]["waived"] is True
    assert response.data["payment"] is None
    assert Subscription.objects.get(user=verified_user).plan.code == "business"
    assert not Payment.objects.exists()


@pytest.mark.parametrize(("credit", "credit_used", "due", "waived"), [
    ("20.00", "20.00", "5.00", False),
    ("22.00", "22.00", "0.00", True),
    ("40.00", "25.00", "0.00", False),
])
def test_the_balance_pays_first(client, halfway, plans, credit, credit_used, due, waived):
    Subscription.objects.filter(pk=halfway.pk).update(credit=Decimal(credit))

    data = preview(client, "business").data

    assert (data["credit_used"], data["amount_due"], data["waived"]) == (credit_used, due, waived)


def test_upgrading_brings_back_suspended_shops(client, halfway, verified_user, plans,
                                               django_capture_on_commit_callbacks):
    make_shops(verified_user, "Pierwszy", "Drugi", "Trzeci")
    make_shops(verified_user, "Zawieszony", status=Shop.Status.SUSPENDED)
    make_shops(verified_user, "Nieudany", status=Shop.Status.SUSPENDED, finished=False)
    payment_id = change(client, django_capture_on_commit_callbacks, "business").data["payment"]["id"]

    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"/api/billing/fake-gateway/{payment_id}/", {"action": "pay"})

    assert Shop.objects.get(slug="zawieszony").status == Shop.Status.ACTIVE
    # A shop whose setup never finished comes back as failed, ready to retry.
    assert Shop.objects.get(slug="nieudany").status == Shop.Status.FAILED


# --- cheaper plan ---


def test_downgrading_suspends_shops_beyond_the_limit_and_credits_the_difference(
    client, halfway, verified_user, plans, django_capture_on_commit_callbacks, mailoutbox,
):
    make_shops(verified_user, "Najstarszy", "Sredni", "Najnowszy")
    make_shops(verified_user, "Testowy", status=Shop.Status.ACTIVE)
    Shop.objects.filter(slug="testowy").update(is_test=True)

    data = preview(client, "start").data
    assert data["direction"] == "downgrade"
    assert (data["credit_added"], data["amount_due"]) == ("10.00", "0.00")
    assert [shop["name"] for shop in data["suspend"]] == ["Sredni", "Najnowszy"]

    response = change(client, django_capture_on_commit_callbacks, "start")

    assert response.status_code == 200
    subscription = Subscription.objects.get(pk=halfway.pk)
    assert (subscription.plan.code, subscription.credit) == ("start", Decimal("10.00"))
    assert subscription.current_period_end == halfway.current_period_end
    statuses = dict(Shop.objects.values_list("slug", "status"))
    assert statuses == {"najstarszy": "active", "sredni": "suspended", "najnowszy": "suspended", "testowy": "active"}
    message = mailoutbox[-1]
    assert message.subject == "Zmieniliśmy plan na Start"
    assert "Sredni, Najnowszy" in message.body
    assert "10,00 PLN" in message.body


def test_the_owner_chooses_which_shops_stay(client, halfway, verified_user, plans, django_capture_on_commit_callbacks):
    oldest, _, newest = make_shops(verified_user, "Najstarszy", "Sredni", "Najnowszy")

    change(client, django_capture_on_commit_callbacks, "start", keep_shops=[newest.pk])

    assert Shop.objects.get(pk=newest.pk).status == Shop.Status.ACTIVE
    assert Shop.objects.get(pk=oldest.pk).status == Shop.Status.SUSPENDED


def test_keeping_more_shops_than_the_plan_allows_is_refused(client, halfway, verified_user, plans):
    shops = make_shops(verified_user, "Jeden", "Dwa", "Trzy")

    data = preview(client, "start", keep_shops=[shop.pk for shop in shops]).data

    assert data["blocked"] == "W planie Start zostawisz najwyżej 1 sklep."


def test_a_shop_being_set_up_cannot_be_suspended(client, halfway, verified_user, plans):
    make_shops(verified_user, "Gotowy")
    make_shops(verified_user, "Zakladany", status=Shop.Status.PROVISIONING)

    data = preview(client, "start").data

    assert data["blocked"].startswith("Poczekaj, aż zakładany sklep będzie gotowy")


def test_less_memory_reaches_running_shops(client, verified_user, plans, monkeypatch,
                                           django_capture_on_commit_callbacks):
    subscribe(verified_user, plans["business"], current_period_start=timezone.now() - timedelta(days=15),
              current_period_end=timezone.now() + timedelta(days=15))
    shop, = make_shops(verified_user, "Sklep")
    refreshed = []
    monkeypatch.setattr("shops.tasks.refresh_shop_resources.delay", refreshed.append)

    change(client, django_capture_on_commit_callbacks, "standard")

    assert refreshed == [shop.pk]


# --- when a change is not possible ---


@pytest.mark.parametrize(("setup", "plan_code", "reason"), [
    ("same", "standard", "To już Twój plan."),
    ("past_due", "business", "Najpierw musi przejść zaległa płatność za obecny plan."),
    ("expired", "business", "Nie masz aktywnego planu. Wybierz plan, żeby go zmieniać."),
])
def test_changes_that_are_refused(client, halfway, plans, setup, plan_code, reason):
    if setup in ("past_due", "expired"):
        Subscription.objects.filter(pk=halfway.pk).update(status=setup)

    assert preview(client, plan_code).data["blocked"] == reason
    response = client.post("/api/billing/subscription/change/", {"plan": plan_code}, format="json")
    assert response.data["detail"] == reason


def test_one_surcharge_at_a_time(client, halfway, plans, django_capture_on_commit_callbacks):
    change(client, django_capture_on_commit_callbacks, "business")

    assert preview(client, "business").data["blocked"] == "Poprzednia zmiana planu czeka jeszcze na płatność."


def test_plans_out_of_offer_cannot_be_chosen(client, halfway, plans):
    Plan.objects.filter(code="business").update(is_active=False)

    assert "plan" in preview(client, "business").data


def test_changing_plans_undoes_a_cancellation(client, halfway, plans, django_capture_on_commit_callbacks):
    Subscription.objects.filter(pk=halfway.pk).update(cancel_at_period_end=True)

    change(client, django_capture_on_commit_callbacks, "start")

    assert Subscription.objects.get(pk=halfway.pk).cancel_at_period_end is False


# --- the balance at renewal ---


def test_renewal_takes_the_balance_first(verified_user, plans, django_capture_on_commit_callbacks):
    subscribe(verified_user, plans["start"], current_period_end=timezone.now() - timedelta(minutes=1),
              credit=Decimal("10.00"))

    services.renew_due()

    payment = Payment.objects.get(user=verified_user)
    assert (payment.amount, payment.credit_used, payment.status) == (Decimal("19.00"), Decimal("10.00"), "paid")
    assert Subscription.objects.get(user=verified_user).credit == Decimal("0.00")


def test_a_large_balance_pays_the_whole_renewal(verified_user, plans, django_capture_on_commit_callbacks, mailoutbox):
    subscribe(verified_user, plans["start"], current_period_end=timezone.now() - timedelta(minutes=1),
              credit=Decimal("40.00"), card_token="")

    with django_capture_on_commit_callbacks(execute=True):
        services.renew_due()

    payment = Payment.objects.get(user=verified_user)
    assert (payment.amount, payment.gateway, payment.status) == (Decimal("0.00"), "credit", "paid")
    subscription = Subscription.objects.get(user=verified_user)
    assert (subscription.status, subscription.credit) == ("active", Decimal("11.00"))
    assert "z salda nadpłaty" in mailoutbox[-1].body


# --- suspended shops ---


def test_suspended_shops_do_not_take_up_the_limit(auth_client, verified_user, plans):
    make_shops(verified_user, "Jeden", "Dwa")
    make_shops(verified_user, "Trzy", status=Shop.Status.SUSPENDED)

    assert auth_client.get("/api/auth/me/").data["can_create_shops"] is True


def test_a_suspended_shop_comes_back_when_there_is_room(auth_client, verified_user, plans,
                                                        django_capture_on_commit_callbacks):
    make_shops(verified_user, "Jeden", "Dwa", "Trzy")
    suspended, = make_shops(verified_user, "Zawieszony", status=Shop.Status.SUSPENDED)

    full = auth_client.post(f"/api/shops/{suspended.pk}/resume/")
    assert full.status_code == 400
    assert "Zmień plan albo usuń inny sklep" in full.data["detail"]

    Shop.objects.filter(slug="trzy").update(status=Shop.Status.DELETED)
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(f"/api/shops/{suspended.pk}/resume/")

    assert response.status_code == 200
    assert response.data["status"] == "active"
    assert auth_client.post(f"/api/shops/{suspended.pk}/resume/").status_code == 409


def test_suspended_shops_have_no_settings(auth_client, verified_user, plans):
    suspended, = make_shops(verified_user, "Zawieszony", status=Shop.Status.SUSPENDED)

    assert auth_client.patch(f"/api/shops/{suspended.pk}/settings/", {"general": {"name": "Inna"}},
                             format="json").status_code == 409
    assert auth_client.get(f"/api/shops/{suspended.pk}/admin-access/").status_code == 409
