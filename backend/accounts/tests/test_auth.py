import re
from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import EmailVerificationCode, User

pytestmark = pytest.mark.django_db

PASSWORD = "Sekretne-haslo-123"


def register(api_client, django_capture_on_commit_callbacks, email="Nowy@Example.com"):
    with django_capture_on_commit_callbacks(execute=True):
        return api_client.post("/api/auth/register/", {"email": email, "password": PASSWORD}, format="json")


def code_from(mail):
    return re.search(r"\b(\d{6})\b", mail.body).group(1)


def test_register_creates_unverified_user_returns_tokens_and_sends_code(
    api_client, django_capture_on_commit_callbacks, mailoutbox,
):
    response = register(api_client, django_capture_on_commit_callbacks)

    assert response.status_code == 201
    assert response.data["user"]["email"] == "nowy@example.com"
    assert response.data["user"]["is_email_verified"] is False
    assert set(response.data["tokens"]) == {"access", "refresh"}
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["nowy@example.com"]


def test_register_starts_an_own_shop_account_unless_joining_a_team(api_client, django_capture_on_commit_callbacks):
    assert register(api_client, django_capture_on_commit_callbacks).data["user"]["purpose"] == "own_shop"

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            "/api/auth/register/", {"email": "obsluga@example.com", "password": PASSWORD, "purpose": "team"},
            format="json",
        )

    assert response.data["user"]["purpose"] == "team"
    assert User.objects.get(email="obsluga@example.com").purpose == User.Purpose.TEAM


def test_the_purpose_can_change_later(auth_client):
    assert auth_client.patch("/api/auth/me/", {"purpose": "team"}, format="json").data["purpose"] == "team"
    assert auth_client.patch("/api/auth/me/", {"purpose": "x"}, format="json").status_code == 400


def test_register_rejects_existing_email_case_insensitively(api_client, user, django_capture_on_commit_callbacks):
    response = register(api_client, django_capture_on_commit_callbacks, email="JAN@example.com")

    assert response.status_code == 400
    assert "email" in response.data


def test_register_rejects_weak_password(api_client):
    response = api_client.post("/api/auth/register/", {"email": "a@example.com", "password": "123"}, format="json")

    assert response.status_code == 400
    assert "password" in response.data


def test_login_ignores_email_case(api_client, user):
    response = api_client.post("/api/auth/login/", {"email": "Jan@Example.com", "password": PASSWORD}, format="json")

    assert response.status_code == 200
    assert "access" in response.data


def test_me_requires_authentication(api_client):
    assert api_client.get("/api/auth/me/").status_code == 401


def test_me_reports_the_plan_and_its_shop_limit(auth_client):
    response = auth_client.get("/api/auth/me/")

    assert response.status_code == 200
    assert response.data["plan"] == "Standard"
    assert response.data["shop_limit"] == 3
    assert response.data["magento_shop_limit"] == 1
    assert response.data["can_create_shops"] is True


def test_me_without_a_plan_cannot_create_shops(api_client, unsubscribed_user):
    api_client.force_authenticate(unsubscribed_user)

    data = api_client.get("/api/auth/me/").data

    assert (data["plan"], data["shop_limit"], data["magento_shop_limit"], data["can_create_shops"]) == (
        None, 0, 0, False,
    )


def test_verify_email_with_correct_code(api_client, django_capture_on_commit_callbacks, mailoutbox):
    tokens = register(api_client, django_capture_on_commit_callbacks).data["tokens"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = api_client.post("/api/auth/verify-email/", {"code": code_from(mailoutbox[0])}, format="json")

    assert response.status_code == 200
    assert response.data["is_email_verified"] is True
    assert not EmailVerificationCode.objects.exists()


def test_verify_email_locks_after_too_many_wrong_codes(
    api_client, django_capture_on_commit_callbacks, mailoutbox, settings,
):
    tokens = register(api_client, django_capture_on_commit_callbacks).data["tokens"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    good_code = code_from(mailoutbox[0])
    wrong_code = "000000" if good_code != "000000" else "111111"

    for _ in range(settings.EMAIL_VERIFICATION_MAX_ATTEMPTS):
        assert api_client.post("/api/auth/verify-email/", {"code": wrong_code}, format="json").status_code == 400
    response = api_client.post("/api/auth/verify-email/", {"code": good_code}, format="json")

    assert response.status_code == 400
    assert "prób" in response.data["detail"]


def test_verify_email_rejects_expired_code(api_client, django_capture_on_commit_callbacks, mailoutbox):
    tokens = register(api_client, django_capture_on_commit_callbacks).data["tokens"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    EmailVerificationCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    response = api_client.post("/api/auth/verify-email/", {"code": code_from(mailoutbox[0])}, format="json")

    assert response.status_code == 400
    assert User.objects.get().is_email_verified is False


def test_resend_verification_respects_cooldown(api_client, user, django_capture_on_commit_callbacks, mailoutbox):
    api_client.force_authenticate(user)

    with django_capture_on_commit_callbacks(execute=True):
        first = api_client.post("/api/auth/resend-verification/")
        second = api_client.post("/api/auth/resend-verification/")

    assert first.status_code == 204
    assert second.status_code == 429
    assert len(mailoutbox) == 1


def test_logout_blacklists_refresh_token(api_client, user):
    tokens = api_client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json").data
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    assert api_client.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code == 205
    assert api_client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code == 401


def test_user_needs_an_email():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="Sekretne-haslo-123")


def test_superuser_is_staff_and_verified(db):
    admin = User.objects.create_superuser(email="Admin@Example.com", password="Sekretne-haslo-123")

    assert admin.is_staff and admin.is_superuser and admin.is_email_verified
    assert str(admin) == "admin@example.com"


def test_logout_with_an_invalid_token_still_succeeds(auth_client):
    response = auth_client.post("/api/auth/logout/", {"refresh": "to-nie-token"}, format="json")

    assert response.status_code == 205


def test_verified_user_gets_no_new_code(auth_client):
    response = auth_client.post("/api/auth/resend-verification/")

    assert response.status_code == 400


def test_verifying_an_already_verified_email_is_harmless(auth_client):
    response = auth_client.post("/api/auth/verify-email/", {"code": "000000"}, format="json")

    assert response.status_code == 200
    assert response.data["is_email_verified"] is True


def test_changing_the_password_signs_out_other_devices(api_client, verified_user, django_capture_on_commit_callbacks,
                                                        mailoutbox):
    login = api_client.post("/api/auth/login/", {"email": verified_user.email, "password": "Sekretne-haslo-123"},
                            format="json").data
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post("/api/auth/change-password/", {
            "current_password": "Sekretne-haslo-123", "new_password": "Zupelnie-Nowe-Haslo-7",
        }, format="json")

    assert response.status_code == 200
    assert set(response.data) == {"access", "refresh"}
    assert api_client.post("/api/auth/refresh/", {"refresh": login["refresh"]}, format="json").status_code == 401
    assert api_client.post("/api/auth/refresh/", {"refresh": response.data["refresh"]}, format="json").status_code == 200
    verified_user.refresh_from_db()
    assert verified_user.check_password("Zupelnie-Nowe-Haslo-7")
    assert mailoutbox[-1].subject == "Hasło do konta zostało zmienione"


@pytest.mark.parametrize(("current", "new", "field"), [
    ("zle-haslo", "Zupelnie-Nowe-Haslo-7", "current_password"),
    ("Sekretne-haslo-123", "Sekretne-haslo-123", "new_password"),
    ("Sekretne-haslo-123", "12345678", "new_password"),
])
def test_password_change_is_checked(auth_client, verified_user, current, new, field):
    response = auth_client.post("/api/auth/change-password/", {"current_password": current, "new_password": new},
                                format="json")

    assert response.status_code == 400
    assert field in response.data
    verified_user.refresh_from_db()
    assert verified_user.check_password("Sekretne-haslo-123")


def test_signing_out_everywhere(api_client, verified_user):
    tokens = [api_client.post("/api/auth/login/", {"email": verified_user.email, "password": "Sekretne-haslo-123"},
                              format="json").data for _ in range(2)]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens[0]['access']}")

    assert api_client.post("/api/auth/logout-everywhere/").status_code == 205
    for pair in tokens:
        assert api_client.post("/api/auth/refresh/", {"refresh": pair["refresh"]}, format="json").status_code == 401
