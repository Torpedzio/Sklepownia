from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import User
from billing import services
from billing.gateways.base import PaymentResult
from billing.models import BillingProfile, Payment, Subscription
from conftest import subscribe

pytestmark = pytest.mark.django_db

RETURN_URL = "http://localhost:8081/billing/return"
PERSON = {
    "kind": "individual", "full_name": "Anna Nowak", "street": "Kwiatowa 1", "postal_code": "00-001", "city": "Warszawa",
}
COMPANY = {**PERSON, "kind": "company", "company_name": "Palarnia sp. z o.o.", "tax_id": "PL 526-000-12-46"}


@pytest.fixture
def client(api_client, unsubscribed_user):
    api_client.force_authenticate(unsubscribed_user)
    return api_client


@pytest.fixture
def user(unsubscribed_user):
    return unsubscribed_user


def checkout(client, captured, **overrides):
    payload = {"plan": "standard", "return_url": RETURN_URL, "accept_terms": True,
               "immediate_start_consent": True, **overrides}
    with captured(execute=True):
        return client.post("/api/billing/checkout/", payload, format="json")


def pay_on_fake_page(client, payment_id, captured, action="pay"):
    with captured(execute=True):
        return client.post(f"/api/billing/fake-gateway/{payment_id}/", {"action": action})


# --- plans and invoice details ---


def test_plans_are_public_cheapest_first(api_client):
    plans = api_client.get("/api/billing/plans/").data

    assert [(p["code"], p["price"], p["max_shops"], p["shop_memory_mb"]) for p in plans] == [
        ("start", "29.00", 1, 512),
        ("standard", "49.00", 3, 512),
        ("business", "99.00", 10, 1024),
    ]
    assert [p["code"] for p in plans if p["is_featured"]] == ["standard"]


def test_hidden_plans_are_not_offered(api_client, plan):
    plan.is_active = False
    plan.save()

    assert "standard" not in [p["code"] for p in api_client.get("/api/billing/plans/").data]


def test_a_person_needs_no_company_details(client):
    response = client.put("/api/billing/profile/", {**PERSON, "company_name": "x", "tax_id": "123"}, format="json")

    assert response.status_code == 200
    assert (response.data["company_name"], response.data["tax_id"]) == ("", "")


def test_a_company_needs_a_valid_nip(client):
    response = client.put("/api/billing/profile/", COMPANY, format="json")

    assert response.status_code == 200
    assert response.data["tax_id"] == "5260001246"


@pytest.mark.parametrize(("data", "field"), [
    ({**COMPANY, "tax_id": "5260001247"}, "tax_id"),
    ({**COMPANY, "tax_id": "123"}, "tax_id"),
    ({**COMPANY, "company_name": " "}, "company_name"),
    ({**PERSON, "postal_code": "00001"}, "postal_code"),
    ({**PERSON, "full_name": ""}, "full_name"),
    ({**PERSON, "kind": "alien"}, "kind"),
])
def test_invalid_invoice_details_are_rejected(client, data, field):
    response = client.put("/api/billing/profile/", data, format="json")

    assert response.status_code == 400
    assert field in response.data


def test_foreign_companies_use_their_own_tax_ids(client):
    data = {**COMPANY, "country": "DE", "tax_id": "DE123456789", "postal_code": "10115"}

    assert client.put("/api/billing/profile/", data, format="json").status_code == 200


def test_billing_needs_a_verified_email(api_client, db):
    api_client.force_authenticate(User.objects.create_user(email="nowy@example.com", password="Sekretne-haslo-123"))

    assert api_client.get("/api/billing/").status_code == 403


# --- first payment ---


def test_checkout_needs_invoice_details(client, django_capture_on_commit_callbacks):
    response = checkout(client, django_capture_on_commit_callbacks)

    assert response.status_code == 400
    assert response.data["detail"] == "Uzupełnij dane do faktury."


def test_checkout_needs_the_terms_and_a_known_return_address(client, django_capture_on_commit_callbacks):
    client.put("/api/billing/profile/", PERSON, format="json")

    response = checkout(client, django_capture_on_commit_callbacks, accept_terms=False, return_url="https://zly.pl/")

    assert set(response.data) == {"accept_terms", "return_url"}


def test_a_person_must_agree_to_start_before_the_withdrawal_period_ends(client, django_capture_on_commit_callbacks):
    client.put("/api/billing/profile/", PERSON, format="json")

    response = checkout(client, django_capture_on_commit_callbacks, immediate_start_consent=False)

    assert response.status_code == 400
    assert "14 dni" in response.data["detail"]


def test_a_company_needs_no_withdrawal_consent(client, django_capture_on_commit_callbacks):
    client.put("/api/billing/profile/", COMPANY, format="json")

    assert checkout(client, django_capture_on_commit_callbacks, immediate_start_consent=False).status_code == 201


def test_paying_activates_the_plan_and_saves_the_card(client, user, django_capture_on_commit_callbacks, mailoutbox):
    client.put("/api/billing/profile/", PERSON, format="json")
    response = checkout(client, django_capture_on_commit_callbacks)
    payment_id = response.data["payment"]["id"]

    assert response.status_code == 201
    assert response.data["payment"]["status"] == "pending"
    assert response.data["redirect_url"].endswith(f"/api/billing/fake-gateway/{payment_id}/")
    assert client.get(response.data["redirect_url"]).status_code == 200

    page = pay_on_fake_page(client, payment_id, django_capture_on_commit_callbacks)

    assert page.status_code == 302
    assert page["Location"] == f"{RETURN_URL}?payment={payment_id}"
    assert client.get(f"/api/billing/payments/{payment_id}/").data["status"] == "paid"
    subscription = Subscription.objects.get(user=user)
    assert subscription.status == Subscription.Status.ACTIVE
    assert subscription.card_token.startswith("fake-")
    assert subscription.current_period_end.date() == (subscription.current_period_start + timedelta(days=30)).date() \
        or subscription.current_period_end.month != subscription.current_period_start.month
    assert subscription.terms_accepted_at and subscription.immediate_start_consent_at
    assert Payment.objects.get(pk=payment_id).billing_details["full_name"] == "Anna Nowak"
    assert mailoutbox[-1].subject == "Plan Standard jest aktywny"
    assert "4242" in mailoutbox[-1].body

    me = client.get("/api/auth/me/").data
    assert (me["plan"], me["can_create_shops"]) == ("Standard", True)


def test_a_declined_first_payment_leaves_no_plan(client, user, django_capture_on_commit_callbacks, mailoutbox):
    client.put("/api/billing/profile/", PERSON, format="json")
    payment_id = checkout(client, django_capture_on_commit_callbacks).data["payment"]["id"]

    pay_on_fake_page(client, payment_id, django_capture_on_commit_callbacks, action="decline")

    payment = client.get(f"/api/billing/payments/{payment_id}/").data
    assert payment["status"] == "failed"
    assert payment["error"] == "Płatność odrzucona na stronie testowej."
    assert Subscription.objects.get(user=user).status == Subscription.Status.INCOMPLETE
    assert mailoutbox == []
    # Trying again is allowed.
    assert checkout(client, django_capture_on_commit_callbacks).status_code == 201


def test_one_active_plan_at_a_time(api_client, verified_user, django_capture_on_commit_callbacks):
    api_client.force_authenticate(verified_user)
    api_client.put("/api/billing/profile/", PERSON, format="json")

    response = checkout(api_client, django_capture_on_commit_callbacks)

    assert response.status_code == 400
    assert response.data["detail"] == "Masz już aktywny plan."


def test_payments_are_private(client, user, api_client, django_capture_on_commit_callbacks):
    client.put("/api/billing/profile/", PERSON, format="json")
    payment_id = checkout(client, django_capture_on_commit_callbacks).data["payment"]["id"]
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    other = type(api_client)()
    other.force_authenticate(stranger)

    assert other.get(f"/api/billing/payments/{payment_id}/").status_code == 404


def test_the_fake_page_only_exists_with_the_fake_gateway(client, settings, django_capture_on_commit_callbacks):
    client.put("/api/billing/profile/", PERSON, format="json")
    payment_id = checkout(client, django_capture_on_commit_callbacks).data["payment"]["id"]
    settings.PAYMENT_GATEWAY = "billing.gateways.tpay.TpayGateway"

    assert client.get(f"/api/billing/fake-gateway/{payment_id}/").status_code == 404


def test_overview_shows_plan_card_details_and_payments(api_client, verified_user):
    api_client.force_authenticate(verified_user)
    api_client.put("/api/billing/profile/", COMPANY, format="json")

    data = api_client.get("/api/billing/").data

    assert data["subscription"]["plan"]["name"] == "Standard"
    assert data["subscription"]["card"] == {"brand": "Visa", "tail": "4242", "expiry": ""}
    assert "card_token" not in str(data)
    assert data["profile"]["company_name"] == "Palarnia sp. z o.o."
    assert data["payments"] == []


# --- applying gateway results ---


def pending_payment(user, plan, kind=Payment.Kind.INITIAL):
    subscription = Subscription.objects.get_or_create(user=user, defaults={"plan": plan})[0]
    return Payment.objects.create(user=user, subscription=subscription, plan=plan, kind=kind, amount=plan.price,
                                  currency="PLN", gateway="fake")


def test_the_same_result_is_applied_once(user, plan):
    payment = pending_payment(user, plan)
    result = PaymentResult(reference=payment.reference, paid=True, amount=plan.price)

    services.apply_result(result)
    end = Subscription.objects.get(user=user).current_period_end
    services.apply_result(result)

    assert Subscription.objects.get(user=user).current_period_end == end


def test_a_short_payment_does_not_activate_the_plan(user, plan):
    payment = pending_payment(user, plan)

    services.apply_result(PaymentResult(reference=payment.reference, paid=True, amount=Decimal("1.00")))

    payment.refresh_from_db()
    assert payment.status == Payment.Status.FAILED
    assert Subscription.objects.get(user=user).status == Subscription.Status.INCOMPLETE


@pytest.mark.parametrize("reference", ["payment-999999", "zamowienie-1", ""])
def test_results_for_unknown_payments_are_ignored(reference):
    assert services.apply_result(PaymentResult(reference=reference, paid=True)) is None


def test_undecided_results_change_nothing(user, plan):
    payment = pending_payment(user, plan)

    services.apply_result(PaymentResult(reference=payment.reference, paid=None))

    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING


# --- renewals ---


def due(user, plan, **fields):
    return subscribe(user, plan, current_period_end=timezone.now() - timedelta(minutes=1), **fields)


def test_renewal_charges_the_saved_card_and_continues_the_period(user, plan, django_capture_on_commit_callbacks,
                                                                 mailoutbox):
    BillingProfile.objects.create(user=user, **{k: v for k, v in PERSON.items()})
    old_end = due(user, plan).current_period_end

    with django_capture_on_commit_callbacks(execute=True):
        services.renew_due()

    subscription = Subscription.objects.get(user=user)
    payment = Payment.objects.get(user=user)
    assert (payment.kind, payment.status) == (Payment.Kind.RENEWAL, Payment.Status.PAID)
    assert payment.period_start == old_end
    assert subscription.current_period_start == old_end
    assert subscription.current_period_end > timezone.now() + timedelta(days=27)
    assert mailoutbox[-1].subject == "Opłaciliśmy plan Standard na kolejny okres"


def test_plans_not_due_are_left_alone(user, plan):
    subscribe(user, plan)

    services.renew_due()

    assert not Payment.objects.exists()


def test_failed_renewals_are_retried_then_the_plan_expires(user, plan, settings, django_capture_on_commit_callbacks,
                                                          mailoutbox):
    settings.FAKE_GATEWAY_DECLINE_RENEWALS = True
    due(user, plan)
    expected_delays = [1, 3, 5]

    for attempt, days in enumerate(expected_delays, start=1):
        with django_capture_on_commit_callbacks(execute=True):
            services.renew_due()
        subscription = Subscription.objects.get(user=user)
        assert subscription.status == Subscription.Status.PAST_DUE
        assert subscription.failed_attempts == attempt
        assert timezone.now() + timedelta(days=days - 1) < subscription.next_attempt_at
        assert not subscription.allows_new_shops
        Subscription.objects.filter(pk=subscription.pk).update(next_attempt_at=timezone.now())

    with django_capture_on_commit_callbacks(execute=True):
        services.renew_due()

    assert Subscription.objects.get(user=user).status == Subscription.Status.EXPIRED
    assert Payment.objects.filter(status=Payment.Status.FAILED).count() == 4
    subjects = [message.subject for message in mailoutbox]
    assert subjects == ["Nie udało się pobrać opłaty za plan Standard"] * 3 + ["Plan Standard wygasł"]


def test_a_successful_retry_brings_the_plan_back(user, plan, settings, django_capture_on_commit_callbacks):
    settings.FAKE_GATEWAY_DECLINE_RENEWALS = True
    due(user, plan)
    services.renew_due()
    settings.FAKE_GATEWAY_DECLINE_RENEWALS = False
    Subscription.objects.filter(user=user).update(next_attempt_at=timezone.now())

    services.renew_due()

    subscription = Subscription.objects.get(user=user)
    assert (subscription.status, subscription.failed_attempts) == (Subscription.Status.ACTIVE, 0)
    assert subscription.current_period_end > timezone.now() + timedelta(days=27)


def test_a_cancelled_plan_ends_with_its_period(api_client, verified_user, django_capture_on_commit_callbacks,
                                               mailoutbox):
    api_client.force_authenticate(verified_user)
    assert api_client.post("/api/billing/subscription/cancel/").data["cancel_at_period_end"] is True
    Subscription.objects.filter(user=verified_user).update(current_period_end=timezone.now())

    with django_capture_on_commit_callbacks(execute=True):
        services.renew_due()

    assert Subscription.objects.get(user=verified_user).status == Subscription.Status.CANCELED
    assert not Payment.objects.exists()
    assert mailoutbox[-1].subject == "Plan Standard zakończył się"


def test_a_cancellation_can_be_undone(api_client, verified_user):
    api_client.force_authenticate(verified_user)
    api_client.post("/api/billing/subscription/cancel/")

    response = api_client.post("/api/billing/subscription/resume/")

    assert response.data["cancel_at_period_end"] is False
    assert api_client.post("/api/billing/subscription/resume/").status_code == 400


def test_cancelling_needs_a_plan(client):
    assert client.post("/api/billing/subscription/cancel/").data["detail"] == "Nie masz jeszcze planu."


def test_a_plan_without_a_saved_card_expires(user, plan):
    due(user, plan, card_token="")

    services.renew_due()

    assert Subscription.objects.get(user=user).status == Subscription.Status.EXPIRED


def test_a_pending_renewal_is_not_charged_twice(user, plan, monkeypatch):
    due(user, plan)
    monkeypatch.setattr(
        "billing.gateways.fake.FakeGateway.charge_saved_card",
        lambda self, payment, payer, token: PaymentResult(reference=payment.reference, paid=None, gateway_id="tr-1"),
    )

    services.renew_due()
    services.renew_due()

    assert Payment.objects.count() == 1


# --- payments whose outcome never reached the platform ---


def paid_at_gateway(monkeypatch, paid=True):
    monkeypatch.setattr(
        "billing.gateways.fake.FakeGateway.fetch_result",
        lambda self, payment: PaymentResult(reference=payment.reference, paid=paid, amount=payment.amount)
        if paid is not None else None,
    )


def started_payment(user, plan):
    payment = pending_payment(user, plan)
    Payment.objects.filter(pk=payment.pk).update(gateway_id="tr-1")
    payment.refresh_from_db()
    return payment


def test_the_billing_page_settles_a_payment_paid_meanwhile(client, user, plan, monkeypatch):
    started_payment(user, plan)
    paid_at_gateway(monkeypatch)

    data = client.get("/api/billing/").data

    assert data["subscription"]["status"] == "active"
    assert data["payments"][0]["status"] == "paid"


def test_reconciling_settles_paid_payments(user, plan, monkeypatch, django_capture_on_commit_callbacks, mailoutbox):
    payment = started_payment(user, plan)
    paid_at_gateway(monkeypatch)

    with django_capture_on_commit_callbacks(execute=True):
        services.reconcile_pending()

    payment.refresh_from_db()
    assert payment.status == Payment.Status.PAID
    assert mailoutbox[-1].subject == "Plan Standard jest aktywny"


def test_reconciling_gives_up_on_payments_nobody_finished(user, plan, monkeypatch):
    payment = started_payment(user, plan)
    paid_at_gateway(monkeypatch, paid=None)
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(days=2))

    services.reconcile_pending()

    payment.refresh_from_db()
    assert (payment.status, payment.error) == (Payment.Status.FAILED, "Płatność nie została dokończona.")


def test_recent_unpaid_payments_keep_waiting(user, plan, monkeypatch):
    payment = started_payment(user, plan)
    paid_at_gateway(monkeypatch, paid=None)

    services.reconcile_pending()

    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING
