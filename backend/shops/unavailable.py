"""
Fallback page for shop addresses with no answering container (suspended, being set up, restarting, or no shop).
Traefik routes those here with the address in X-Forwarded-Host (infra/shops/traefik/fallback.yml).
"""

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from .choices import Language
from .models import Shop

# "closed": suspended or down, "opening": being set up.
TEXTS = {
    Language.PL: {
        "closed": {"sign": "Nieczynne", "text": "Sklep jest chwilowo niedostępny. Zajrzyj tu później."},
        "opening": {
            "sign": "Wkrótce otwarcie",
            "text": "Sklep jest właśnie przygotowywany. Zajrzyj tu za kilka minut.",
        },
    },
    Language.EN: {
        "closed": {"sign": "Closed", "text": "The shop is temporarily unavailable. Please come back later."},
        "opening": {"sign": "Opening soon", "text": "The shop is being set up. Please come back in a few minutes."},
    },
    Language.DE: {
        "closed": {
            "sign": "Geschlossen",
            "text": "Der Shop ist vorübergehend nicht erreichbar. Schau bitte später wieder vorbei.",
        },
        "opening": {
            "sign": "Bald geöffnet",
            "text": "Der Shop wird gerade eingerichtet. Schau bitte in ein paar Minuten wieder vorbei.",
        },
    },
}
# Seconds.
RETRY_AFTER = {"closed": 3600, "opening": 300}
# "closed", "opening" or "missing": lets the monitor tell this page from the shop's own answer.
UNAVAILABLE_HEADER = "X-Shop-Unavailable"
OPENING = {Shop.Status.PENDING, Shop.Status.PROVISIONING}


def shop_at(host):
    """`host` like "palarnia.sklepy.pl:8080"; deleted shops don't count."""
    slug, dot, domain = host.split(":")[0].strip().lower().partition(".")
    if not dot or domain != settings.SHOPS_BASE_DOMAIN.lower():
        return None
    return Shop.objects.select_related("config").exclude(status=Shop.Status.DELETED).filter(slug=slug).first()


# Any method, so a form posted to a shop that is down gets the page too; nothing here changes state.
@csrf_exempt
@never_cache
def shop_unavailable(request):
    # Traefik overwrites any client-sent value, so it can be trusted.
    host = request.headers.get("X-Forwarded-Host", "").split(",")[0]
    shop = shop_at(host) if host else None
    if shop is None:
        response = render(request, "shops/unavailable.html", {"lang": "pl", "missing": True}, status=404)
        response[UNAVAILABLE_HEADER] = "missing"
        return response
    state = "opening" if shop.status in OPENING else "closed"
    config = getattr(shop, "config", None)
    language = config.language if config else Language.PL
    context = {"lang": language[:2], "name": shop.name, **TEXTS.get(language, TEXTS[Language.PL])[state]}
    response = render(request, "shops/unavailable.html", context, status=503)
    response["Retry-After"] = str(RETRY_AFTER[state])
    response[UNAVAILABLE_HEADER] = state
    return response
