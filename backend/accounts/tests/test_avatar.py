from io import BytesIO

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

pytestmark = pytest.mark.django_db

URL = "/api/auth/avatar/"


def picture(size=(800, 600), fmt="JPEG", color="teal", exif=None, name="me.jpg"):
    output = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(output, fmt, **({"exif": exif} if exif else {}))
    return SimpleUploadedFile(name, output.getvalue(), content_type=f"image/{fmt.lower()}")


def upload(client, file, capture):
    with capture(execute=True):
        return client.put(URL, {"avatar": file}, format="multipart")


@pytest.fixture
def client(api_client, user):
    api_client.force_authenticate(user)
    return api_client


def test_upload_stores_a_square_webp_without_metadata(client, user, django_capture_on_commit_callbacks):
    exif = Image.Exif()
    exif[0x010F] = "Telefon"  # Make
    response = upload(client, picture(exif=exif), django_capture_on_commit_callbacks)

    assert response.status_code == 200
    user.refresh_from_db()
    assert response.data["avatar_url"] == f"http://testserver/media/{user.avatar.name}"
    with default_storage.open(user.avatar.name) as file:
        stored = Image.open(file)
        assert (stored.format, stored.size) == ("WEBP", (512, 512))
        assert not stored.getexif()


def test_new_picture_replaces_and_removes_the_old_file(client, user, django_capture_on_commit_callbacks):
    upload(client, picture(), django_capture_on_commit_callbacks)
    user.refresh_from_db()
    first = user.avatar.name

    upload(client, picture(fmt="PNG", name="me.png", color="orange"), django_capture_on_commit_callbacks)
    user.refresh_from_db()

    assert user.avatar.name != first
    assert not default_storage.exists(first)
    assert default_storage.exists(user.avatar.name)


def test_delete_clears_the_picture(client, user, django_capture_on_commit_callbacks):
    upload(client, picture(), django_capture_on_commit_callbacks)
    user.refresh_from_db()
    name = user.avatar.name

    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(URL)

    assert response.status_code == 200
    assert response.data["avatar_url"] is None
    assert not default_storage.exists(name)


@pytest.mark.parametrize(
    "file, message",
    [
        (SimpleUploadedFile("notes.jpg", b"to nie jest obraz"), "To nie jest zdjęcie"),
        (picture(fmt="BMP", name="me.bmp"), "Wybierz zdjęcie JPG, PNG, WebP albo GIF."),
    ],
)
def test_rejects_files_that_are_not_supported_pictures(client, user, file, message,
                                                       django_capture_on_commit_callbacks):
    response = upload(client, file, django_capture_on_commit_callbacks)

    assert response.status_code == 400
    assert response.data["avatar"][0].startswith(message)
    user.refresh_from_db()
    assert not user.avatar


def test_rejects_huge_resolutions_before_decoding(client, django_capture_on_commit_callbacks):
    response = upload(client, picture(size=(8000, 6000), fmt="PNG", name="big.png"),
                      django_capture_on_commit_callbacks)

    assert response.status_code == 400
    assert response.data["avatar"] == ["Zdjęcie ma za dużą rozdzielczość."]


def test_requires_sign_in(api_client):
    assert api_client.put(URL, {}, format="multipart").status_code == 401


def test_picture_is_served_publicly_and_cached(client, user, django_capture_on_commit_callbacks):
    upload(client, picture(), django_capture_on_commit_callbacks)
    user.refresh_from_db()
    client.force_authenticate(None)

    response = client.get(f"/media/{user.avatar.name}")

    assert response.status_code == 200
    assert response["Content-Type"] == "image/webp"
    assert "immutable" in response["Cache-Control"]


@pytest.mark.parametrize("name", ["nope.webp", "../settings.py", "0" * 32 + ".webp"])
def test_unknown_or_odd_names_are_not_found(api_client, name):
    assert api_client.get(f"/media/avatars/{name}").status_code == 404
