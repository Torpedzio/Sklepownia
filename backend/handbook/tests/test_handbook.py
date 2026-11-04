from pathlib import Path

import pytest
from django.conf import settings

from handbook import pages

pytestmark = pytest.mark.django_db


@pytest.fixture
def docs(tmp_path, settings):
    settings.HANDBOOK_ROOT = str(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(
        "# Start\n\nZobacz [architekturę](docs/architektura.md#stany-sklepu) i [kod](backend/shops/models.py).\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "architektura.md").write_text("# Architektura\n\n## Stany sklepu\n", encoding="utf-8")
    return tmp_path


def test_index_renders_readme_and_rewrites_links(client, docs, settings):
    settings.DEBUG = True

    response = client.get("/docs/")

    assert response.status_code == 200
    html = response.content.decode()
    assert '<h1 id="start">Start</h1>' in html
    assert 'href="/docs/architektura/#stany-sklepu"' in html
    # Source files can't be opened from the docs, so they stay as plain paths.
    assert '<span class="path" title="Plik w repozytorium">kod</span>' in html


def test_headings_get_unicode_anchors(client, docs, settings):
    settings.DEBUG = True

    html = client.get("/docs/architektura/").content.decode()

    assert 'id="stany-sklepu"' in html
    assert 'aria-current="page">Architektura' in html


def test_missing_page_or_file_is_404(client, docs, settings):
    settings.DEBUG = True

    assert client.get("/docs/nie-ma-takiej/").status_code == 404
    # Listed in the menu, but its file isn't in this repository copy.
    assert client.get("/docs/backend/").status_code == 404


def test_outside_debug_only_staff_can_read(client, docs, settings, verified_user):
    settings.DEBUG = False

    assert client.get("/docs/").status_code == 302

    verified_user.is_staff = True
    verified_user.save()
    client.force_login(verified_user)
    assert client.get("/docs/").status_code == 200


@pytest.mark.skipif(not Path(settings.HANDBOOK_ROOT).is_dir(), reason="repository not mounted")
def test_every_listed_page_exists_in_the_repository():
    for page in pages.PAGES:
        assert pages.render(page) is not None, page.path
