"""
The project documentation (Markdown files in the repository) rendered as web pages under /docs/.

Files are read on every request, so an edited file shows up after a page refresh.
"""

import posixpath
from dataclasses import dataclass
from pathlib import Path

import markdown
from django.conf import settings
from django.urls import reverse
from markdown.extensions import Extension
from markdown.extensions.toc import slugify_unicode
from markdown.treeprocessors import Treeprocessor


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    # Relative to the repository root.
    path: str


# Menu order. A new document becomes visible here once it is listed.
PAGES = [
    Page("", "Start", "README.md"),
    Page("architektura", "Architektura", "docs/architektura.md"),
    Page("uruchomienie", "Uruchomienie lokalne", "docs/uruchomienie.md"),
    Page("backend", "Backend", "docs/backend.md"),
    Page("api", "API", "docs/api.md"),
    Page("aplikacja-mobilna", "Aplikacja mobilna", "docs/aplikacja-mobilna.md"),
    Page("serwer-sklepow", "Serwer sklepów", "infra/shops/README.md"),
    Page("platnosci", "Płatności i plany", "docs/platnosci.md"),
    Page("obsluga", "Obsługa na co dzień", "docs/obsluga.md"),
    Page("rozwoj", "Rozwój projektu", "docs/rozwoj.md"),
    Page("ograniczenia-i-plan", "Ograniczenia i plan", "docs/ograniczenia-i-plan.md"),
]
PAGES_BY_SLUG = {page.slug: page for page in PAGES}
PAGES_BY_PATH = {page.path: page for page in PAGES}


def page_url(page):
    return reverse("handbook-page", kwargs={"slug": page.slug}) if page.slug else reverse("handbook-index")


def render(page):
    """Return the page as HTML, or None when its file is missing."""
    source = Path(settings.HANDBOOK_ROOT) / page.path
    if not source.is_file():
        return None
    return markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc", LinkExtension(page)],
        # Same anchors as GitHub, so links like `obsluga.md#zmiana-sieci-lub-adresu-ip` keep working.
        extension_configs={"toc": {"slugify": slugify_unicode}},
        output_format="html",
    )


class LinkExtension(Extension):
    def __init__(self, page):
        super().__init__()
        self.page = page

    def extendMarkdown(self, md):
        md.treeprocessors.register(LinkRewriter(md, self.page), "handbook_links", 0)


class LinkRewriter(Treeprocessor):
    """
    Points links between documents at their pages. Links to source files can't be followed here,
    so they become plain paths.
    """

    def __init__(self, md, page):
        super().__init__(md)
        self.page = page

    def run(self, root):
        for link in root.iter("a"):
            href = link.get("href", "")
            if not href or href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target, _, anchor = href.partition("#")
            path = posixpath.normpath(posixpath.join(posixpath.dirname(self.page.path), target))
            page = PAGES_BY_PATH.get(path)
            if page is not None:
                link.set("href", page_url(page) + (f"#{anchor}" if anchor else ""))
            else:
                _as_path(link)


def _as_path(link):
    link.tag = "span"
    link.attrib.clear()
    link.set("class", "path")
    link.set("title", "Plik w repozytorium")

