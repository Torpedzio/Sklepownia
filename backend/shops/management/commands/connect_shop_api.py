from django.core.management.base import BaseCommand

from shops.models import Shop
from shops.provisioning import get_provisioner
from shops.remote import ShopApiError
from shops.services import current_operation


class Command(BaseCommand):
    help = (
        "Daje działającym sklepom nowy klucz do ich API, z którego korzysta aplikacja (np. sklepom sprzed tej "
        "funkcji albo takim, w których właściciel usunął klucz w panelu), i sprawdza połączenie. Sklep Magento "
        "dostaje przy tym kontener z aktualnego obrazu i nie odpowiada przez kilkanaście sekund. Uruchamiaj w "
        "kontenerze workera, który ma dostęp do Dockera."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="Tylko te sklepy (adresy); domyślnie wszystkie działające.")
        parser.add_argument("--check", action="store_true", help="Tylko sprawdza połączenie, bez nowych kluczy.")

    def handle(self, *args, slugs, check, **options):
        shops = Shop.objects.filter(status=Shop.Status.ACTIVE).order_by("pk")
        if slugs:
            shops = shops.filter(slug__in=slugs)
            for slug in sorted(set(slugs) - set(shops.values_list("slug", flat=True))):
                self.stderr.write(f"{slug}: nie ma takiego działającego sklepu")
        for shop in shops:
            if not check and current_operation(shop) is not None:
                self.stdout.write(f"{shop.slug}: pominięty, worker właśnie coś w nim robi")
                continue
            provisioner = get_provisioner(shop.platform)
            try:
                if not check:
                    provisioner.step_generate_api_keys(shop)
                provisioner.api(shop).ping()
            except ShopApiError as exc:
                self.stderr.write(f"{shop.slug}: brak połączenia ({exc})")
            except Exception as exc:
                self.stderr.write(f"{shop.slug}: nie udało się ({exc})")
            else:
                self.stdout.write(self.style.SUCCESS(f"{shop.slug}: połączony"))
