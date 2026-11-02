import re

from .models import Shop

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$")

# Subdomains the platform itself may need.
RESERVED_SLUGS = {
    "admin", "api", "app", "auth", "blog", "cdn", "dashboard", "dev", "docs", "ftp", "help",
    "imap", "mail", "media", "ns1", "ns2", "panel", "pop", "smtp", "staging", "static",
    "status", "support", "test", "traefik", "www",
}


def normalize_slug(slug):
    return slug.strip().lower()


def slug_error(slug):
    """Return why `slug` can't be used for a new shop, or None if it's free."""
    if not SLUG_PATTERN.match(slug) or "--" in slug:
        return "Adres może mieć 3–30 znaków: małe litery, cyfry i myślniki (nie na początku ani na końcu)."
    if slug in RESERVED_SLUGS:
        return "Ten adres jest zarezerwowany."
    if Shop.objects.filter(slug=slug).exclude(status=Shop.Status.DELETED).exists():
        return "Ten adres jest już zajęty."
    return None
