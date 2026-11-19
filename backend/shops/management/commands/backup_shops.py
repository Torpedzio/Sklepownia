from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import filesizeformat

from shops import backups
from shops.models import Shop, ShopBackup
from shops.provisioning.base import NothingToBackUp, ProvisioningError


class Command(BaseCommand):
    help = (
        "Robi teraz kopie zapasowe sklepów (działających i zawieszonych). Bez listy sklepów także porządkuje "
        "repozytorium jak w nocy: usuwa kopie, których już się nie trzyma. Uruchamiaj w kontenerze workera, "
        "który ma dostęp do Dockera."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="Tylko te sklepy (adresy); domyślnie wszystkie.")

    def handle(self, *args, slugs, **options):
        if not backups.enabled():
            raise CommandError("SHOPS_BACKUP_PASSWORD jest puste, więc kopie zapasowe są wyłączone.")
        shops = Shop.objects.filter(status__in=backups.BACKED_UP).order_by("pk")
        if slugs:
            shops = shops.filter(slug__in=slugs)
            for slug in sorted(set(slugs) - set(shops.values_list("slug", flat=True))):
                self.stderr.write(f"{slug}: nie ma takiego działającego ani zawieszonego sklepu")
        for shop in shops:
            try:
                backup = backups.back_up(shop, ShopBackup.Kind.MANUAL)
            except NothingToBackUp:
                self.stdout.write(f"{shop.slug}: pominięty, sklep nie ma plików")
                continue
            except ProvisioningError:
                self.stderr.write(f"{shop.slug}: nie udało się (szczegóły w panelu admina, Shop backups)")
                continue
            self.stdout.write(self.style.SUCCESS(f"{shop.slug}: kopia {backup.pk}, {filesizeformat(backup.size)}"))
        if not slugs:
            removed = backups.maintain()
            self.stdout.write(f"Usunięte kopie spoza okresu przechowywania: {removed}")
