"""
Third-party plugins/modules installed on demand (e.g. a payment operator), pinned by version and SHA-256 so a file
changed at the source never reaches a shop. Cached by the worker in SHOPS_PACKAGE_CACHE; shops get them from it.
"""

import hashlib
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from .base import ProvisioningError

logger = logging.getLogger(__name__)

TIMEOUT = 60
USER_AGENT = "Sklepownia-provisioner"


@dataclass(frozen=True)
class Package:
    # In the genitive, for messages: "wtyczki Przelewy24", "modułu PayU".
    title: str
    # The archive's top folder: the plugin's or module's name in the shop.
    folder: str
    version: str
    url: str
    sha256: str

    @property
    def filename(self):
        return f"{self.folder}-{self.version}.zip"


def fetch(package):
    """The zip archive (bytes), checked against its SHA-256."""
    cached = Path(settings.SHOPS_PACKAGE_CACHE) / package.filename
    if cached.is_file():
        data = cached.read_bytes()
        if _matches(data, package):
            return data
        logger.warning("Cached %s does not match its checksum, downloading it again", cached)
    data = _download(package)
    if not _matches(data, package):
        logger.error("Download of %s %s from %s does not match its checksum", package.folder, package.version,
                     package.url)
        raise ProvisioningError(
            f"Pobrany plik {package.title} różni się od wersji sprawdzonej przez nas, więc go nie instalujemy. "
            "Spróbuj ponownie później."
        )
    cached.parent.mkdir(parents=True, exist_ok=True)
    partial = cached.with_name(cached.name + ".part")
    partial.write_bytes(data)
    partial.replace(cached)
    return data


def _download(package):
    request = urllib.request.Request(package.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Downloading %s failed: %s", package.url, exc)
        raise ProvisioningError(f"Nie udało się pobrać {package.title}. Spróbuj ponownie za chwilę.") from exc


def _matches(data, package):
    return hashlib.sha256(data).hexdigest() == package.sha256
