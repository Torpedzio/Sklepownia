from django.core.management.base import BaseCommand

from shops.models import Shop
from shops.provisioning import get_provisioner


class Command(BaseCommand):
    help = (
        "Przenosi działające sklepy pod adresy wynikające z bieżących ustawień, np. po zmianie "
        "SHOPS_BASE_DOMAIN. Uruchamiaj w kontenerze workera, który ma dostęp do Dockera."
    )

    def handle(self, *args, **options):
        for shop in Shop.objects.filter(status=Shop.Status.ACTIVE).order_by("pk"):
            try:
                previous = get_provisioner(shop.platform).update_address(shop)
            except Exception as exc:
                self.stderr.write(f"{shop.slug}: nie udało się przenieść ({exc})")
                continue
            if previous is None:
                self.stdout.write(f"{shop.slug}: pominięty, brak kontenera sklepu")
            elif previous == shop.url:
                self.stdout.write(f"{shop.slug}: bez zmian, {shop.url}")
            else:
                self.stdout.write(self.style.SUCCESS(f"{shop.slug}: {previous} → {shop.url}"))
