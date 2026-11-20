import pytest
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import delete_account
from shops import history, services
from shops.models import Shop, ShopEvent, ShopInvitation, ShopMember, ShopOperation

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


def person(email, **fields):
    return User.objects.create_user(email=email, password="Sekretne-haslo-123", is_email_verified=True, **fields)


def entries(client, shop, **params):
    return client.get(f"/api/shops/{shop.pk}/history/", params).data


def lines(client, shop):
    return [(event["title"], event["detail"], event["actor_role"]) for event in entries(client, shop)["events"]]


def test_a_new_shop_starts_its_history(auth_client, shop):
    [event] = entries(auth_client, shop)["events"]

    assert event["title"] == "Założenie sklepu"
    assert event["actor"]["email"] == "anna@example.com"
    assert event["actor_role"] == "owner"
    assert event["status"] is None


def test_changes_in_the_shop_are_recorded_with_their_outcome(auth_client, shop, verified_user,
                                                            django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        services.start_operation(shop, verified_user, ShopOperation.Kind.REMOVE_SAMPLE_PRODUCTS)
    # Refreshing the settings is routine, not a change.
    with django_capture_on_commit_callbacks(execute=True):
        services.start_operation(shop, verified_user, ShopOperation.Kind.SYNC_SETTINGS)
    ShopOperation.objects.filter(kind=ShopOperation.Kind.REMOVE_SAMPLE_PRODUCTS).update(
        status=ShopOperation.Status.FAILED, error="Sklep nie odpowiedział.",
    )

    event = entries(auth_client, shop)["events"][0]

    assert (event["title"], event["status"], event["error"]) == (
        "Usunięcie przykładowych produktów", "failed", "Sklep nie odpowiedział.",
    )
    assert ShopEvent.objects.filter(kind=ShopEvent.Kind.OPERATION).count() == 1


def test_settings_changes_list_the_fields(auth_client, shop, verified_user):
    operation = ShopOperation.objects.create(
        shop=shop, kind=ShopOperation.Kind.UPDATE_SETTINGS, requested_by=verified_user,
        changes={"region": {"currency": "EUR"}},
    )
    history.record_operation(operation)

    event = entries(auth_client, shop)["events"][0]

    assert (event["title"], event["detail"]) == ("Zmiana ustawień", "Waluta")


def test_the_team_story(auth_client, shop, django_capture_on_commit_callbacks):
    def invite(email):
        with django_capture_on_commit_callbacks(execute=True):
            auth_client.post(f"/api/shops/{shop.pk}/team/invitations/", {"email": email}, format="json")

    ola, jan = person("ola@example.com", first_name="Ola", last_name="Nowak"), person("jan@example.com")
    invite("ola@example.com")
    invite("ola@example.com")
    client_for(ola).post(f"/api/invitations/{ShopInvitation.objects.get().pk}/accept/")
    invite("jan@example.com")
    client_for(jan).post(f"/api/invitations/{ShopInvitation.objects.get().pk}/decline/")
    invite("ewa@example.com")
    auth_client.delete(f"/api/shops/{shop.pk}/team/invitations/{ShopInvitation.objects.get().pk}/")
    auth_client.delete(f"/api/shops/{shop.pk}/team/members/{ola.pk}/")
    ShopMember.objects.create(shop=shop, user=jan)
    client_for(jan).post(f"/api/shops/{shop.pk}/leave/")

    assert lines(auth_client, shop) == [
        ("Odejście z zespołu", "", "staff"),
        ("Usunięcie z zespołu", "Ola Nowak", "owner"),
        ("Cofnięcie zaproszenia", "ewa@example.com", "owner"),
        ("Zaproszenie do zespołu", "ewa@example.com", "owner"),
        ("Odrzucenie zaproszenia", "jan@example.com", "staff"),
        ("Zaproszenie do zespołu", "jan@example.com", "owner"),
        ("Dołączenie do zespołu", "", "staff"),
        ("Ponowne zaproszenie do zespołu", "ola@example.com", "owner"),
        ("Zaproszenie do zespołu", "ola@example.com", "owner"),
        ("Założenie sklepu", "", "owner"),
    ]


def test_a_deleted_account_leaves_without_its_name(auth_client, shop):
    ola = person("ola@example.com", first_name="Ola")
    ShopMember.objects.create(shop=shop, user=ola)

    delete_account(ola)

    event = entries(auth_client, shop)["events"][0]
    assert (event["title"], event["actor"], event["actor_role"]) == (
        "Usunięcie konta i odejście z zespołu", None, "deleted",
    )


def test_the_platform_suspends_and_resumes(auth_client, shop, verified_user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        services.suspend_shops([shop])
    with django_capture_on_commit_callbacks(execute=True):
        services.resume_shop(shop, verified_user)

    assert lines(auth_client, shop)[:2] == [
        ("Przywrócenie sklepu", "", "owner"),
        ("Zawieszenie sklepu", "Sklep nie mieścił się w planie właściciela.", "system"),
    ]


def test_older_entries_come_a_page_at_a_time(auth_client, shop):
    for number in range(35):
        history.record(shop, ShopEvent.Kind.INVITATION_SENT, email=f"o{number}@example.com")

    first = entries(auth_client, shop)
    second = entries(auth_client, shop, before=first["events"][-1]["id"])

    assert (len(first["events"]), first["has_more"]) == (30, True)
    assert (len(second["events"]), second["has_more"]) == (6, False)
    assert second["events"][-1]["title"] == "Założenie sklepu"
    assert {event["id"] for event in first["events"]}.isdisjoint(event["id"] for event in second["events"])


def test_only_the_owner_reads_the_history(shop):
    helper = person("ola@example.com")
    ShopMember.objects.create(shop=shop, user=helper)

    assert client_for(helper).get(f"/api/shops/{shop.pk}/history/").status_code == 403
