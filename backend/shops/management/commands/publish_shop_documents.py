from django.core.management.base import BaseCommand

from shops import documents, services
from shops.models import Shop, ShopOperation, ShopSettings


class Command(BaseCommand):
    help = (
        "Zleca publikację regulaminu i polityki prywatności z aktualnych wzorów w sklepach, które mają je z aplikacji, "
        "np. po zmianie przepisów i wzorów (shops/documents.py, VERSION). Domyślnie tylko sklepy ze starszą wersją. "
        "Właściciel widzi to w historii zmian sklepu."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="Tylko te sklepy (adresy); domyślnie wszystkie działające.")
        parser.add_argument(
            "--all", dest="everything", action="store_true", help="Także sklepy, które mają już aktualną wersję.",
        )

    def handle(self, *args, slugs, everything, **options):
        shops = Shop.objects.filter(status=Shop.Status.ACTIVE).order_by("pk")
        if slugs:
            shops = shops.filter(slug__in=slugs)
        stored = {settings.shop_id: settings.values for settings in ShopSettings.objects.filter(shop__in=shops)}
        queued = 0
        for shop in shops:
            values = stored.get(shop.pk, {}).get("documents", {})
            if not values.get("managed"):
                continue
            if values.get("version") == documents.VERSION and not everything:
                continue
            try:
                services.start_operation(shop, None, ShopOperation.Kind.PUBLISH_DOCUMENTS)
            except (services.ShopNotActive, services.OperationInProgress):
                self.stderr.write(f"{shop.slug}: sklep jest zajęty, uruchom polecenie ponownie za chwilę")
                continue
            queued += 1
            self.stdout.write(f"{shop.slug}: zlecono")
        self.stdout.write(self.style.SUCCESS(f"Zlecone publikacje: {queued} (wersja wzorów {documents.VERSION})."))
