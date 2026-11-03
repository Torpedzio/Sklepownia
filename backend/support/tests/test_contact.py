import pytest

from support.models import ContactMessage

pytestmark = pytest.mark.django_db


def payload(**overrides):
    return {"name": "Jan", "email": "jan@example.com", "topic": "question",
            "message": "Czy mogę podpiąć własną domenę?", **overrides}


def test_anyone_can_send_contact_message(api_client, django_capture_on_commit_callbacks, mailoutbox, settings):
    settings.CONTACT_EMAIL = "biuro@example.com"
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post("/api/contact/", payload(), format="json")

    assert response.status_code == 201
    assert ContactMessage.objects.get().user is None
    assert mailoutbox[0].to == ["biuro@example.com"]
    assert mailoutbox[0].reply_to == ["jan@example.com"]


def test_logged_in_sender_is_linked(auth_client, verified_user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post("/api/contact/", payload(), format="json")

    assert ContactMessage.objects.get().user == verified_user


def test_message_too_short_is_rejected(api_client):
    response = api_client.post("/api/contact/", payload(message="Hej"), format="json")

    assert response.status_code == 400
    assert "message" in response.data
