"""Account deletion: shops and plan go, paid payments stay without anything that identifies the owner."""

import logging

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from accounts.models import User
from billing import services as billing
from billing.gateways.base import PaymentResult
from billing.models import BillingProfile, Payment, Subscription
from shops.models import Shop, ShopConfig, ShopSettings, ShopTemplate

pytestmark = pytest.mark.django_db

PASSWORD = "Sekretne-haslo-123"


def make_shop(user, name, status=Shop.Status.ACTIVE):
    shop = Shop.objects.create(owner=user, name=name, slug=name.lower(), status=status)
    ShopConfig.objects.create(shop=shop, industry="food", template=ShopTemplate.objects.get(slug="storefront"),
                              category_count=3, contact_email="kontakt@example.com")
    ShopSettings.objects.create(shop=shop, values={"bank_account": "PL61109010140000071219812874"})
    return shop


def pay(user, plan, status=Payment.Status.PAID):
    return Payment.objects.create(
        user=user, subscription=user.subscription, plan=plan, kind=Payment.Kind.INITIAL, amount=plan.price,
        currency="PLN", gateway="fake", status=status, billing_details={"full_name": "Anna Nowak"},
    )


def delete(client, captured, password=PASSWORD):
    with captured(execute=True):
        return client.post("/api/auth/delete-account/", {"password": password}, format="json")


def test_deleting_the_account_removes_shops_plan_and_personal_data(
    api_client, verified_user, plan, django_capture_on_commit_callbacks, mailoutbox,
):
    tokens = api_client.post("/api/auth/login/", {"email": verified_user.email, "password": PASSWORD},
                             format="json").data
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    verified_user.first_name = "Anna"
    verified_user.avatar = default_storage.save("avatars/" + "a" * 32 + ".webp", ContentFile(b"webp"))
    verified_user.save()
    BillingProfile.objects.create(user=verified_user, kind="individual", full_name="Anna Nowak",
                                  street="Polna 1", postal_code="00-001", city="Warszawa")
    paid = pay(verified_user, plan)
    make_shop(verified_user, "Palarnia")
    make_shop(verified_user, "Zawieszony", status=Shop.Status.SUSPENDED)
    make_shop(verified_user, "Stary", status=Shop.Status.DELETED)

    assert delete(api_client, django_capture_on_commit_callbacks, "zle-haslo").data == {
        "password": ["Hasło jest nieprawidłowe."],
    }
    assert Shop.objects.count() == 3

    response = delete(api_client, django_capture_on_commit_callbacks)

    assert response.status_code == 204
    user = User.objects.get(pk=verified_user.pk)
    assert user.email == f"deleted-{user.pk}@deleted.invalid"
    assert (user.first_name, user.avatar.name, user.is_active) == ("", "", False)
    assert not user.has_usable_password()
    assert user.deleted_at is not None
    assert not default_storage.exists(verified_user.avatar.name)
    assert not Shop.objects.exists()
    assert not ShopSettings.objects.exists()
    subscription = Subscription.objects.get(user=user)
    assert subscription.status == Subscription.Status.CANCELED
    assert (subscription.card_token, subscription.card_tail) == ("", "")
    assert not subscription.allows_new_shops
    assert not BillingProfile.objects.exists()
    paid.refresh_from_db()
    assert (paid.status, paid.billing_details) == (Payment.Status.PAID, {"full_name": "Anna Nowak"})
    [mail] = mailoutbox
    assert (mail.to, mail.subject) == (["anna@example.com"], "Konto zostało usunięte")
    assert "Palarnia" in mail.body and "Zawieszony" in mail.body and "Stary" not in mail.body
    assert api_client.get("/api/auth/me/").status_code == 401
    api_client.credentials()
    assert api_client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code == 401
    assert api_client.post("/api/auth/login/", {"email": "anna@example.com", "password": PASSWORD},
                           format="json").status_code == 401
    with django_capture_on_commit_callbacks(execute=True):
        again = api_client.post("/api/auth/register/", {"email": "anna@example.com", "password": PASSWORD},
                                format="json")
    assert again.status_code == 201


@pytest.mark.parametrize("status", [Shop.Status.PENDING, Shop.Status.PROVISIONING])
def test_a_shop_being_set_up_has_to_finish_first(
    auth_client, verified_user, django_capture_on_commit_callbacks, status,
):
    make_shop(verified_user, "Nowy", status=status)

    response = delete(auth_client, django_capture_on_commit_callbacks)

    assert response.status_code == 409
    assert response.data["detail"] == (
        "Sklep „Nowy” jest właśnie zakładany. Poczekaj, aż będzie gotowy, i spróbuj ponownie."
    )
    verified_user.refresh_from_db()
    assert verified_user.is_active and verified_user.email == "anna@example.com"
    assert Shop.objects.get().status == status


def test_administrators_are_deleted_in_the_admin_panel(auth_client, verified_user, django_capture_on_commit_callbacks):
    User.objects.filter(pk=verified_user.pk).update(is_staff=True)

    response = delete(auth_client, django_capture_on_commit_callbacks)

    assert response.status_code == 409
    assert User.objects.get(pk=verified_user.pk).is_active


def test_a_payment_left_waiting_is_dropped_and_a_late_payment_is_flagged_for_a_refund(
    auth_client, verified_user, plan, django_capture_on_commit_callbacks, caplog,
):
    waiting = pay(verified_user, plan, status=Payment.Status.PENDING)

    delete(auth_client, django_capture_on_commit_callbacks)

    waiting.refresh_from_db()
    assert (waiting.status, waiting.error) == (Payment.Status.FAILED, "Konto zostało usunięte przed opłaceniem.")
    with caplog.at_level(logging.ERROR):
        billing.apply_result(PaymentResult(reference=waiting.reference, paid=True, amount=plan.price))
    assert f"Payment {waiting.pk} was paid after it had failed" in caplog.text
    assert Subscription.objects.get(user=verified_user).status == Subscription.Status.CANCELED
