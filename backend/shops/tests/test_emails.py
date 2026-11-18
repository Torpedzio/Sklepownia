import pytest

from accounts.models import User
from shops.models import Shop
from shops.tasks import send_admin_access_email

pytestmark = pytest.mark.django_db


def payload(**overrides):
    return {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront", **overrides}


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks, mailoutbox):
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload(), format="json").data["id"]
    return Shop.objects.get(pk=shop_id)


def html_of(message):
    return message.alternatives[0][0]


def test_finished_shop_sends_its_details_and_admin_login(shop, verified_user, mailoutbox):
    [message] = mailoutbox
    credentials = shop.credentials

    assert message.to == [verified_user.email]
    assert message.subject == "Sklep „Mój Sklep” jest gotowy"
    for body in (message.body, html_of(message)):
        assert shop.admin_url in body
        assert credentials.admin_login in body
        assert credentials.admin_password in body
        assert "Odzież i moda" in body
        assert "Storefront" in body
    assert 'href="https://moj-sklep.localhost"' in html_of(message)


def test_failed_setup_sends_nothing(auth_client, settings, django_capture_on_commit_callbacks, mailoutbox):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "install_wordpress"

    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post("/api/shops/", payload(), format="json")

    assert mailoutbox == []


def test_retried_setup_sends_the_login_when_it_succeeds(
    auth_client, settings, django_capture_on_commit_callbacks, mailoutbox,
):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "health_check"
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload(), format="json").data["id"]
    assert mailoutbox == []

    settings.FAKE_PROVISIONER_FAIL_AT_STEP = ""
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post(f"/api/shops/{shop_id}/retry/")

    assert [message.subject for message in mailoutbox] == ["Sklep „Mój Sklep” jest gotowy"]


def test_login_can_be_sent_again(shop, auth_client, verified_user, mailoutbox):
    response = auth_client.post(f"/api/shops/{shop.pk}/send-admin-access/")

    assert response.status_code == 202
    assert response.data["sent_to"] == verified_user.email
    assert mailoutbox[-1].subject == "Dane logowania do sklepu „Mój Sklep”"
    assert shop.credentials.admin_password in mailoutbox[-1].body


def test_sending_again_is_limited(shop, auth_client):
    statuses = [auth_client.post(f"/api/shops/{shop.pk}/send-admin-access/").status_code for _ in range(6)]

    assert statuses == [202] * 5 + [429]


def test_nothing_to_send_before_the_shop_is_ready(auth_client, settings, django_capture_on_commit_callbacks):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "install_wordpress"
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload(), format="json").data["id"]

    assert auth_client.post(f"/api/shops/{shop_id}/send-admin-access/").status_code == 409


def test_someone_elses_login_cannot_be_requested(shop, api_client, mailoutbox):
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    api_client.force_authenticate(stranger)

    assert api_client.post(f"/api/shops/{shop.pk}/send-admin-access/").status_code == 404
    assert len(mailoutbox) == 1


def test_new_password_comes_by_e_mail(shop, auth_client, django_capture_on_commit_callbacks, mailoutbox):
    old_password = shop.credentials.admin_password

    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post(f"/api/shops/{shop.pk}/reset-admin-password/")

    message = mailoutbox[-1]
    new_password = Shop.objects.get(pk=shop.pk).credentials.admin_password
    assert message.subject == "Nowe hasło do panelu sklepu „Mój Sklep”"
    assert new_password in message.body
    assert old_password not in message.body
    # Only the login: the shop's details came with the first e-mail.
    assert "Twój sklep" not in html_of(message)


def test_failed_password_change_sends_nothing(shop, auth_client, settings, django_capture_on_commit_callbacks, mailoutbox):
    settings.FAKE_PROVISIONER_FAIL_AT_STEP = "reset_admin_password"

    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post(f"/api/shops/{shop.pk}/reset-admin-password/")

    assert len(mailoutbox) == 1


def test_deleted_shops_get_no_mail(shop, mailoutbox):
    Shop.objects.filter(pk=shop.pk).update(status=Shop.Status.DELETED)

    send_admin_access_email(shop.pk, "resend")

    assert len(mailoutbox) == 1


@pytest.mark.parametrize(("platform", "note"), [
    ("woocommerce", "Płatności, wysyłkę, podatki i regulamin ustawisz w aplikacji, w ustawieniach sklepu."),
    ("prestashop", "Płatności i regulamin ustawisz w aplikacji, w ustawieniach sklepu. "
                   "Wysyłkę i podatki w panelu sklepu."),
    ("magento", "Płatności, wysyłkę, podatki i regulamin ustawisz w aplikacji, w ustawieniach sklepu."),
])
def test_the_e_mail_says_what_the_app_sets_on_the_shops_platform(shop, mailoutbox, platform, note):
    from shops.emails import admin_access_message

    shop.platform = platform
    message = admin_access_message(shop, "resend")

    # Every platform has its note, so no shop is left without its login (Magento once was).
    assert note in message.body
    assert note in html_of(message)
