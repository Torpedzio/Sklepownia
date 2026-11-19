from django.core.management.base import BaseCommand

from shops.models import Shop
from shops.provisioning import get_provisioner
from shops.services import current_operation


class Command(BaseCommand):
    help = (
        "Zastępuje kontenery działających sklepów, które nie są takie, jak worker założyłby je teraz: np. sprzed "
        "healthchecka, ze starym obrazem albo starym limitem pamięci. Pliki sklepu są w wolumenie, a baza w serwerze "
        "baz, więc nic nie ginie; sklep nie odpowiada przez kilkanaście sekund. Uruchamiaj w kontenerze workera, "
        "który ma dostęp do Dockera."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="Tylko te sklepy (adresy); domyślnie wszystkie działające.")
        parser.add_argument("--dry-run", action="store_true", help="Tylko wypisuje, które kontenery by zastąpił.")

    def handle(self, *args, slugs, dry_run, **options):
        shops = Shop.objects.filter(status=Shop.Status.ACTIVE).order_by("pk")
        if slugs:
            shops = shops.filter(slug__in=slugs)
            for slug in sorted(set(slugs) - set(shops.values_list("slug", flat=True))):
                self.stderr.write(f"{slug}: nie ma takiego działającego sklepu")
        for shop in shops:
            if current_operation(shop) is not None:
                self.stdout.write(f"{shop.slug}: pominięty, worker właśnie coś w nim robi")
                continue
            provisioner = get_provisioner(shop.platform)
            routed = True
            try:
                outdated = provisioner.container_outdated(shop)
                if outdated and not dry_run:
                    routed = provisioner.start_shop(shop)
            except Exception as exc:
                self.stderr.write(f"{shop.slug}: nie udało się ({exc})")
                continue
            if not outdated:
                self.stdout.write(f"{shop.slug}: bez zmian")
            elif dry_run:
                self.stdout.write(f"{shop.slug}: do zastąpienia")
            elif routed:
                self.stdout.write(self.style.SUCCESS(f"{shop.slug}: kontener zastąpiony"))
            else:
                self.stderr.write(
                    f"{shop.slug}: kontener zastąpiony, ale sklep jeszcze nie odpowiada (docker logs shop-{shop.pk})"
                )
