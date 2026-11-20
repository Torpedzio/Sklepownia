from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import delete_account
from billing.models import Plan, Subscription
from shops.models import Shop, ShopInvitation, ShopMember

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(auth_client, django_capture_on_commit_callbacks):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "storefront"}
    with django_capture_on_commit_callbacks(execute=True):
        shop_id = auth_client.post("/api/shops/", payload, format="json").data["id"]
    return Shop.objects.get(pk=shop_id)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def helper(db):
    return User.objects.create_user(email="pomocnik@example.com", password="Sekretne-haslo-123", is_email_verified=True)


@pytest.fixture
def staff_client(shop, helper):
    ShopMember.objects.create(shop=shop, user=helper)
    return client_for(helper)


def test_each_person_sees_their_role(auth_client, staff_client, shop):
    assert [item["role"] for item in auth_client.get("/api/shops/").data] == ["owner"]
    assert [(item["id"], item["role"]) for item in staff_client.get("/api/shops/").data] == [(shop.pk, "staff")]
    assert staff_client.get(f"/api/shops/{shop.pk}/").data["role"] == "staff"


def test_a_stranger_does_not_see_the_shop(shop):
    stranger = User.objects.create_user(email="obcy@example.com", password="Sekretne-haslo-123", is_email_verified=True)

    assert client_for(stranger).get("/api/shops/").data == []
    assert client_for(stranger).get(f"/api/shops/{shop.pk}/sales/").status_code == 404


def test_the_staff_sees_the_sales(staff_client, shop):
    assert staff_client.get(f"/api/shops/{shop.pk}/sales/").status_code == 200
    assert staff_client.post(f"/api/shops/{shop.pk}/sales/refresh/").status_code == 202


@pytest.mark.parametrize("method, path", [
    ("delete", ""),
    ("post", "retry/"),
    ("post", "resume/"),
    ("get", "admin-access/"),
    ("post", "send-admin-access/"),
    ("get", "settings/"),
    ("patch", "settings/"),
    ("post", "settings/refresh/"),
    ("post", "documents/preview/"),
    ("post", "reset-admin-password/"),
    ("post", "remove-sample-products/"),
    ("get", "operations/"),
    ("get", "checklist/"),
    ("get", "backups/"),
    ("post", "backups/"),
    ("post", "backups/1/restore/"),
])
def test_everything_else_is_only_for_the_owner(staff_client, shop, method, path):
    response = getattr(staff_client, method)(f"/api/shops/{shop.pk}/{path}", {}, format="json")

    assert response.status_code == 403
    assert response.data["detail"] == "Tylko właściciel sklepu może to zrobić."
    assert Shop.objects.get(pk=shop.pk).status == Shop.Status.ACTIVE


def test_the_owners_plan_counts_only_the_shops_they_own(staff_client, shop, verified_user):
    # The helper has no plan of their own, so serving a shop gives them none to create shops with.
    payload = {"name": "Drugi", "slug": "drugi-sklep", "industry": "fashion", "template": "storefront"}

    assert staff_client.post("/api/shops/", payload, format="json").status_code == 402
    assert list(verified_user.shops.all()) == [shop]


def test_a_deleted_shop_is_gone_for_the_staff_too(auth_client, staff_client, shop):
    auth_client.delete(f"/api/shops/{shop.pk}/")

    assert staff_client.get("/api/shops/").data == []


def test_a_deleted_account_leaves_the_teams(staff_client, shop, helper):
    delete_account(helper)

    assert not ShopMember.objects.filter(user=helper).exists()


# Invitations


def invite(client, shop, email, capture):
    with capture(execute=True):
        return client.post(f"/api/shops/{shop.pk}/team/invitations/", {"email": email}, format="json")


def on_plan(user, code):
    Subscription.objects.filter(user=user).update(plan=Plan.objects.get(code=code))


def test_the_owner_invites_by_email(auth_client, shop, django_capture_on_commit_callbacks, settings):
    settings.APP_URL = "https://app.example.com"
    mail.outbox.clear()

    response = invite(auth_client, shop, " Nowa.Osoba@Example.com ", django_capture_on_commit_callbacks)

    assert response.status_code == 201
    assert response.data["email"] == "nowa.osoba@example.com"
    assert response.data["expired"] is False
    [message] = mail.outbox
    assert message.to == ["nowa.osoba@example.com"]
    assert message.subject == "Zaproszenie do sklepu „Mój Sklep”"
    assert "zaprasza Cię do zespołu sklepu „Mój Sklep”" in message.body
    # No account yet, so the link leads to signing up with the address filled in.
    assert "https://app.example.com/sign-up?email=nowa.osoba%40example.com" in message.body
    assert "https://app.example.com/sign-up?email=nowa.osoba%40example.com" in message.alternatives[0][0]


def test_an_existing_account_is_sent_to_sign_in(auth_client, shop, helper, django_capture_on_commit_callbacks):
    mail.outbox.clear()

    invite(auth_client, shop, helper.email, django_capture_on_commit_callbacks)

    assert "/sign-in?email=pomocnik%40example.com" in mail.outbox[0].body


def test_inviting_again_renews_the_term(auth_client, shop, django_capture_on_commit_callbacks):
    invite(auth_client, shop, "nowa@example.com", django_capture_on_commit_callbacks)
    ShopInvitation.objects.update(expires_at=timezone.now() - timedelta(days=1))
    mail.outbox.clear()

    response = invite(auth_client, shop, "nowa@example.com", django_capture_on_commit_callbacks)

    assert response.status_code == 201
    assert ShopInvitation.objects.get().expired is False
    assert len(mail.outbox) == 1


@pytest.mark.parametrize("email, message", [
    ("anna@example.com", "To Twój adres: właściciel jest w zespole od początku."),
    ("pomocnik@example.com", "Ta osoba jest już w zespole sklepu."),
])
def test_owner_and_members_are_not_invited(auth_client, staff_client, shop, email, message,
                                           django_capture_on_commit_callbacks):
    response = invite(auth_client, shop, email, django_capture_on_commit_callbacks)

    assert response.status_code == 400
    assert response.data["email"] == [message]


def test_the_plan_limits_the_team_counting_invitations(auth_client, shop, verified_user,
                                                       django_capture_on_commit_callbacks):
    on_plan(verified_user, "start")
    for number in range(4):
        ShopMember.objects.create(shop=shop, user=User.objects.create_user(email=f"o{number}@example.com", password="x"))
    assert invite(auth_client, shop, "piata@example.com", django_capture_on_commit_callbacks).status_code == 201

    response = invite(auth_client, shop, "szosta@example.com", django_capture_on_commit_callbacks)

    assert response.status_code == 409
    assert response.data["detail"].startswith("Twój plan pozwala na 5 osób z obsługi w sklepie")
    # Renewing an invitation already counted still works.
    assert invite(auth_client, shop, "piata@example.com", django_capture_on_commit_callbacks).status_code == 201
    team = auth_client.get(f"/api/shops/{shop.pk}/team/").data
    assert (team["limit"], team["used"]) == (5, 5)


def test_business_has_no_limit(auth_client, shop, verified_user):
    on_plan(verified_user, "business")

    assert auth_client.get(f"/api/shops/{shop.pk}/team/").data["limit"] is None


def test_without_a_plan_nobody_can_be_invited(auth_client, shop, verified_user, django_capture_on_commit_callbacks):
    Subscription.objects.filter(user=verified_user).delete()

    response = invite(auth_client, shop, "nowa@example.com", django_capture_on_commit_callbacks)

    assert response.status_code == 409


def test_the_team_overview(auth_client, staff_client, shop, django_capture_on_commit_callbacks):
    invite(auth_client, shop, "nowa@example.com", django_capture_on_commit_callbacks)

    team = auth_client.get(f"/api/shops/{shop.pk}/team/").data

    assert team["owner"]["email"] == "anna@example.com"
    assert [member["email"] for member in team["members"]] == ["pomocnik@example.com"]
    assert [invitation["email"] for invitation in team["invitations"]] == ["nowa@example.com"]
    assert (team["limit"], team["used"]) == (20, 2)


@pytest.mark.parametrize("method, path", [
    ("get", "team/"),
    ("post", "team/invitations/"),
    ("delete", "team/invitations/1/"),
    ("delete", "team/members/1/"),
])
def test_only_the_owner_manages_the_team(staff_client, shop, method, path):
    response = getattr(staff_client, method)(f"/api/shops/{shop.pk}/{path}", {"email": "x@example.com"}, format="json")

    assert response.status_code == 403


@pytest.fixture
def invited(auth_client, shop, django_capture_on_commit_callbacks):
    """A verified account with an invitation to the shop."""
    user = User.objects.create_user(email="nowa@example.com", password="Sekretne-haslo-123", is_email_verified=True)
    invite(auth_client, shop, user.email, django_capture_on_commit_callbacks)
    return user


def test_the_invited_person_sees_and_accepts(invited, shop):
    client = client_for(invited)
    [invitation] = client.get("/api/invitations/").data
    assert invitation["shop"]["name"] == "Mój Sklep"
    assert invitation["invited_by"]["email"] == "anna@example.com"

    response = client.post(f"/api/invitations/{invitation['id']}/accept/")

    assert response.status_code == 200
    assert (response.data["id"], response.data["role"]) == (shop.pk, "staff")
    assert client.get("/api/invitations/").data == []
    assert [item["id"] for item in client.get("/api/shops/").data] == [shop.pk]


def test_declining_removes_the_invitation(invited, shop):
    client = client_for(invited)
    invitation_id = client.get("/api/invitations/").data[0]["id"]

    assert client.post(f"/api/invitations/{invitation_id}/decline/").status_code == 204
    assert not ShopInvitation.objects.exists()
    assert client.get("/api/shops/").data == []


def test_others_and_unverified_accounts_see_nothing(invited, helper):
    invitation = ShopInvitation.objects.get()
    assert client_for(helper).get("/api/invitations/").data == []
    assert client_for(helper).post(f"/api/invitations/{invitation.pk}/accept/").status_code == 404

    User.objects.filter(pk=invited.pk).update(is_email_verified=False)
    invited.refresh_from_db()
    assert client_for(invited).get("/api/invitations/").data == []


def test_expired_and_deleted_shop_invitations_are_gone(auth_client, invited, shop):
    ShopInvitation.objects.update(expires_at=timezone.now())
    assert client_for(invited).get("/api/invitations/").data == []

    ShopInvitation.objects.update(expires_at=timezone.now() + timedelta(days=1))
    auth_client.delete(f"/api/shops/{shop.pk}/")
    assert client_for(invited).get("/api/invitations/").data == []


def test_accepting_a_full_team_is_refused(invited, shop, verified_user):
    on_plan(verified_user, "start")
    for number in range(5):
        ShopMember.objects.create(shop=shop, user=User.objects.create_user(email=f"o{number}@example.com", password="x"))

    response = client_for(invited).post(f"/api/invitations/{ShopInvitation.objects.get().pk}/accept/")

    assert response.status_code == 409
    assert not ShopMember.objects.filter(user=invited).exists()


def test_the_owner_revokes_an_invitation(auth_client, invited, shop):
    invitation = ShopInvitation.objects.get()

    assert auth_client.delete(f"/api/shops/{shop.pk}/team/invitations/{invitation.pk}/").status_code == 204
    assert client_for(invited).get("/api/invitations/").data == []
    assert auth_client.delete(f"/api/shops/{shop.pk}/team/invitations/{invitation.pk}/").status_code == 404


def test_the_owner_removes_a_member(auth_client, staff_client, shop, helper):
    assert auth_client.delete(f"/api/shops/{shop.pk}/team/members/{helper.pk}/").status_code == 204
    assert staff_client.get("/api/shops/").data == []
    assert auth_client.delete(f"/api/shops/{shop.pk}/team/members/{helper.pk}/").status_code == 404


def test_the_staff_leaves_and_the_owner_cannot(auth_client, staff_client, shop):
    assert auth_client.post(f"/api/shops/{shop.pk}/leave/").status_code == 409

    assert staff_client.post(f"/api/shops/{shop.pk}/leave/").status_code == 204
    assert staff_client.get("/api/shops/").data == []


def test_a_revoked_invitation_sends_nothing(auth_client, shop, django_capture_on_commit_callbacks):
    from shops.tasks import send_invitation_email

    invite(auth_client, shop, "nowa@example.com", django_capture_on_commit_callbacks)
    invitation_id = ShopInvitation.objects.get().pk
    ShopInvitation.objects.all().delete()
    mail.outbox.clear()

    send_invitation_email(invitation_id)

    assert mail.outbox == []
