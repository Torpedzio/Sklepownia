from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.shortcuts import render as render_template
from django.urls import reverse

from . import pages


def page(request, slug=""):
    # The docs describe internals, so outside development only staff may read them.
    if not settings.DEBUG and not request.user.is_staff:
        return redirect_to_login(request.get_full_path(), reverse("admin:login"))
    current = pages.PAGES_BY_SLUG.get(slug)
    html = pages.render(current) if current else None
    if html is None:
        raise Http404("Nie ma takiej strony dokumentacji.")
    return render_template(request, "handbook/page.html", {
        "content": html,
        "current": current,
        "menu": [(item, pages.page_url(item)) for item in pages.PAGES],
    })
