import hashlib
import urllib.error

import pytest

from shops.provisioning import packages
from shops.provisioning.base import ProvisioningError
from shops.provisioning.packages import Package

ARCHIVE = b"PK\x03\x04 archiwum wtyczki"
# Taken before conftest swaps it for a guard: one test runs it with the network cut off.
REAL_DOWNLOAD = packages._download


def package():
    return Package(title="wtyczki Przelewy24", folder="woo-przelewy24", version="1.2.1",
                   url="https://example.com/woo-przelewy24-1.2.1.zip", sha256=hashlib.sha256(ARCHIVE).hexdigest())


class Site:
    """Stands in for the maker's site: answers with `answer` and counts the downloads."""

    def __init__(self):
        self.answer = ARCHIVE
        self.count = 0

    def __call__(self, wanted):
        self.count += 1
        return self.answer


@pytest.fixture
def site(monkeypatch):
    fake = Site()
    monkeypatch.setattr(packages, "_download", fake)
    return fake


@pytest.fixture
def cached(tmp_path):
    return tmp_path / "packages" / "woo-przelewy24-1.2.1.zip"


def test_a_package_is_downloaded_once_and_kept(site, cached):
    assert packages.fetch(package()) == ARCHIVE
    assert packages.fetch(package()) == ARCHIVE

    assert site.count == 1
    assert cached.read_bytes() == ARCHIVE


def test_a_download_that_does_not_match_its_checksum_is_refused_and_not_kept(site, cached):
    site.answer = b"PK\x03\x04 podmieniona wtyczka"

    with pytest.raises(ProvisioningError, match="różni się od wersji sprawdzonej"):
        packages.fetch(package())

    assert not cached.exists()


def test_a_damaged_copy_is_downloaded_again(site, cached):
    cached.parent.mkdir()
    cached.write_bytes(b"uszkodzony")

    assert packages.fetch(package()) == ARCHIVE
    assert site.count == 1
    assert cached.read_bytes() == ARCHIVE


def test_a_failed_download_says_what_could_not_be_fetched(monkeypatch):
    def unreachable(request, timeout):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(packages, "_download", REAL_DOWNLOAD)
    monkeypatch.setattr(packages.urllib.request, "urlopen", unreachable)

    with pytest.raises(ProvisioningError, match="Nie udało się pobrać wtyczki Przelewy24"):
        packages.fetch(package())
