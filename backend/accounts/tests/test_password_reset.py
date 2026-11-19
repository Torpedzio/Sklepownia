"""Forgotten password: a code by e-mail, then a new password with it."""

import re
from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import EmailVerificationCode, PasswordResetCode

pytestmark = pytest.mark.django_db

OLD = "Sekretne-haslo-123"
NEW = "Zupelnie-Nowe-Haslo-7"


def ask(client, captured, email):
    with captured(execute=True):
        return client.post("/api/auth/password-reset/", {"email": email}, format="json")


def reset(client, captured, email, code, password=NEW):
    with captured(execute=True):
        return client.post("/api/auth/password-reset/confirm/",
                           {"email": email, "code": code, "new_password": password}, format="json")


def code_from(mail):
    return re.search(r"\b(\d{6})\b", mail.body).group(1)


def test_a_code_by_e_mail_sets_a_new_password_and_signs_in(api_client, verified_user,
                                                             django_capture_on_commit_callbacks, mailoutbox):
    other_device = api_client.post("/api/auth/login/", {"email": verified_user.email, "password": OLD},
                                   format="json").data

    assert ask(api_client, django_capture_on_commit_callbacks, " ANNA@example.com ").status_code == 204
    [mail] = mailoutbox
    assert mail.to == [verified_user.email]
    assert mail.subject == "Kod do ustawienia nowego hasła"
    assert "Jeśli to nie Ty, zignoruj tę wiadomość" in mail.body
    code = code_from(mail)
    assert code in mail.alternatives[0][0]

    response = reset(api_client, django_capture_on_commit_callbacks, verified_user.email, code)

    assert response.status_code == 200
    assert set(response.data) == {"access", "refresh"}
    verified_user.refresh_from_db()
    assert verified_user.check_password(NEW)
    assert api_client.post("/api/auth/refresh/", {"refresh": other_device["refresh"]}, format="json").status_code == 401
    assert mailoutbox[-1].subject == "Hasło do konta zostało zmienione"
    assert not PasswordResetCode.objects.exists()
    again = reset(api_client, django_capture_on_commit_callbacks, verified_user.email, code, "Jeszcze-Inne-Haslo-9")
    assert again.data == {"code": ["Kod wygasł. Poproś o nowy kod."]}


def test_unknown_addresses_look_the_same(api_client, django_capture_on_commit_callbacks, mailoutbox):
    assert ask(api_client, django_capture_on_commit_callbacks, "nikt@example.com").status_code == 204
    assert mailoutbox == []

    response = reset(api_client, django_capture_on_commit_callbacks, "nikt@example.com", "123456")
    assert (response.status_code, response.data) == (400, {"code": ["Kod wygasł. Poproś o nowy kod."]})


def test_asking_again_within_a_minute_sends_nothing_new(api_client, verified_user,
                                                        django_capture_on_commit_callbacks, mailoutbox):
    ask(api_client, django_capture_on_commit_callbacks, verified_user.email)
    ask(api_client, django_capture_on_commit_callbacks, verified_user.email)
    assert len(mailoutbox) == 1

    PasswordResetCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
    ask(api_client, django_capture_on_commit_callbacks, verified_user.email)
    assert len(mailoutbox) == 2
    # Only the newest code works (the two codes may match by chance).
    old, new = code_from(mailoutbox[0]), code_from(mailoutbox[1])
    if old != new:
        assert reset(api_client, django_capture_on_commit_callbacks, verified_user.email, old).data == {
            "code": ["Nieprawidłowy kod."],
        }
    assert reset(api_client, django_capture_on_commit_callbacks, verified_user.email, new).status_code == 200


def test_wrong_codes_lock_the_code(api_client, verified_user, django_capture_on_commit_callbacks, mailoutbox):
    ask(api_client, django_capture_on_commit_callbacks, verified_user.email)
    code = code_from(mailoutbox[0])
    wrong = "000000" if code != "000000" else "111111"

    assert reset(api_client, django_capture_on_commit_callbacks, verified_user.email, wrong).data == {
        "code": ["Nieprawidłowy kod."],
    }
    for _ in range(4):
        reset(api_client, django_capture_on_commit_callbacks, verified_user.email, wrong)

    response = reset(api_client, django_capture_on_commit_callbacks, verified_user.email, code)
    assert response.data == {"code": ["Przekroczono liczbę prób. Poproś o nowy kod."]}
    verified_user.refresh_from_db()
    assert verified_user.check_password(OLD)


def test_an_expired_code_does_not_work(api_client, verified_user, django_capture_on_commit_callbacks, mailoutbox):
    ask(api_client, django_capture_on_commit_callbacks, verified_user.email)
    PasswordResetCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    response = reset(api_client, django_capture_on_commit_callbacks, verified_user.email, code_from(mailoutbox[0]))

    assert response.data == {"code": ["Kod wygasł. Poproś o nowy kod."]}


def test_a_weak_password_keeps_the_code_usable(api_client, verified_user, django_capture_on_commit_callbacks,
                                               mailoutbox):
    ask(api_client, django_capture_on_commit_callbacks, verified_user.email)
    code = code_from(mailoutbox[0])

    weak = reset(api_client, django_capture_on_commit_callbacks, verified_user.email, code, "12345678")
    assert weak.status_code == 400
    assert "new_password" in weak.data

    assert reset(api_client, django_capture_on_commit_callbacks, verified_user.email, code).status_code == 200


def test_resetting_also_confirms_the_address(api_client, user, django_capture_on_commit_callbacks, mailoutbox):
    EmailVerificationCode.objects.create(user=user, code_hash="x", expires_at=timezone.now() + timedelta(minutes=5))
    ask(api_client, django_capture_on_commit_callbacks, user.email)

    reset(api_client, django_capture_on_commit_callbacks, user.email, code_from(mailoutbox[0]))

    user.refresh_from_db()
    assert user.is_email_verified is True
    assert not EmailVerificationCode.objects.filter(user=user).exists()


def test_asking_for_codes_is_limited_per_ip_address(api_client, django_capture_on_commit_callbacks):
    statuses = [ask(api_client, django_capture_on_commit_callbacks, f"ktos{i}@example.com").status_code
                for i in range(6)]

    assert statuses == [204] * 5 + [429]
