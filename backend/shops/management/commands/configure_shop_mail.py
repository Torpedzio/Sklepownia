from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from shops.models import Shop
from shops.provisioning import get_provisioner


class Command(BaseCommand):
    help = (
        "Ustawia w działających sklepach wysyłkę e-maili przez serwer pocztowy platformy (SHOPS_SMTP_*), "
        "np. dla sklepów założonych wcześniej albo po zmianie serwera. Kontener sklepu ze starszego obrazu "
        "jest najpierw odtwarzany. Uruchamiaj w kontenerze workera, który ma dostęp do Dockera."
    )

    def add_arguments(self, parser):
        parser.add_argument("slugs", nargs="*", help="Tylko te sklepy (adresy); domyślnie wszystkie działające.")

    def handle(self, *args, slugs, **options):
        if not settings.SHOPS_SMTP_HOST:
            raise CommandError("SHOPS_SMTP_HOST jest puste, więc sklepy nie mają serwera pocztowego.")
        shops = Shop.objects.filter(status=Shop.Status.ACTIVE).order_by("pk")
        if slugs:
            shops = shops.filter(slug__in=slugs)
            missing = set(slugs) - set(shops.values_list("slug", flat=True))
            for slug in sorted(missing):
                self.stderr.write(f"{slug}: nie ma takiego działającego sklepu")
        for shop in shops:
            try:
                configured = get_provisioner(shop.platform).configure_mail(shop)
            except Exception as exc:
                self.stderr.write(f"{shop.slug}: nie udało się ustawić poczty ({exc})")
                continue
            if configured:
                self.stdout.write(self.style.SUCCESS(f"{shop.slug}: wysyła jako {shop.mail_sender}"))
            else:
                self.stdout.write(f"{shop.slug}: pominięty, brak kontenera sklepu")
        suspended = Shop.objects.filter(status=Shop.Status.SUSPENDED).count()
        if suspended and not slugs:
            self.stdout.write(
                f"Zawieszone sklepy ({suspended}) są pominięte: uruchom polecenie ponownie po ich przywróceniu."
            )
