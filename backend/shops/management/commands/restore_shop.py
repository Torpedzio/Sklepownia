from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import filesizeformat
from django.utils import formats, timezone

from shops import backups, services
from shops.models import Shop
from shops.provisioning import get_provisioner
from shops.provisioning.base import ProvisioningError


class Command(BaseCommand):
    help = (
        "Przywraca sklep z kopii zapasowej: działający sklep (najpierw powstaje kopia jego obecnego stanu) "
        f"albo usunięty w ciągu ostatnich {settings.SHOPS_BACKUP_DELETED_DAYS} dni. "
        "Bez --backup wypisuje kopie sklepu. "
        "Uruchamiaj w kontenerze workera, który ma dostęp do Dockera."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "shop", help="Numer sklepu albo adres (slug) działającego sklepu; usunięty sklep tylko numerem.",
        )
        parser.add_argument("--backup", type=int, help="Numer kopii z listy, do której wrócić.")

    def handle(self, *args, shop, backup, **options):
        shop = self._find(shop)
        if backup is None:
            self._list(shop)
            return
        chosen = backups.restorable(shop).filter(pk=backup).first()
        if chosen is None:
            raise CommandError(f"Sklep {shop.slug} nie ma kopii {backup}. Bez --backup zobaczysz jego kopie.")
        if not backups.enabled():
            raise CommandError("SHOPS_BACKUP_PASSWORD jest puste, więc kopie zapasowe są wyłączone.")
        if shop.status == Shop.Status.ACTIVE:
            self._restore_running(shop, chosen)
        elif shop.status == Shop.Status.DELETED:
            self._bring_back(shop, chosen)
        else:
            raise CommandError(
                f"Sklep jest w stanie „{shop.get_status_display()}”. Przywrócić można działający albo usunięty sklep."
            )

    def _find(self, value):
        shops = Shop.objects.select_related("owner")
        shop = shops.filter(pk=int(value)).first() if value.isdigit() else (
            shops.exclude(status=Shop.Status.DELETED).filter(slug=value).first()
        )
        if shop is None:
            raise CommandError(f"Nie ma sklepu {value}.")
        return shop

    def _list(self, shop):
        listed = list(backups.restorable(shop))
        self.stdout.write(
            f"{shop.name} ({shop.slug}, nr {shop.pk}, {shop.get_status_display()}), właściciel {shop.owner.email}"
        )
        if not listed:
            self.stdout.write("Brak kopii.")
        for item in listed:
            taken = formats.date_format(timezone.localtime(item.created_at), "j E Y, H:i")
            self.stdout.write(f"  {item.pk:>6}  {taken}  {item.get_kind_display()}, {filesizeformat(item.size)}")

    def _restore_running(self, shop, backup):
        if services.current_operation(shop) is not None:
            raise CommandError("Na sklepie trwa właśnie inna operacja. Spróbuj za kilka minut.")
        try:
            before = backups.restore(shop, backup)
        except ProvisioningError as exc:
            raise CommandError(f"{exc} Szczegóły w logach workera.") from exc
        self.stdout.write(self.style.SUCCESS(
            f"{shop.slug}: przywrócony z kopii {backup.pk}. Stan sprzed przywrócenia to kopia {before.pk}."
        ))

    def _bring_back(self, shop, backup):
        if Shop.objects.exclude(status=Shop.Status.DELETED).filter(slug=shop.slug).exists():
            raise CommandError(f"Adres {shop.slug} ma już inny sklep, więc tego nie da się przywrócić pod nim.")
        try:
            get_provisioner(shop.platform).restore_backup(shop, backup.snapshot_id)
        except Exception as exc:
            raise CommandError(f"Nie udało się przywrócić sklepu ({exc}).") from exc
        # Back from deleted on purpose: the state machine lets nobody else do that.
        Shop.objects.filter(pk=shop.pk).update(status=Shop.Status.ACTIVE, updated_at=timezone.now())
        shop.refresh_from_db()
        backups.read_again(shop)
        self.stdout.write(self.style.SUCCESS(f"{shop.slug}: przywrócony z kopii {backup.pk}, działa pod {shop.url}."))
        plan = services.active_plan(shop.owner)
        if plan is None or services.paid_shop_count(shop.owner) > plan.max_shops:
            self.stdout.write(self.style.WARNING(
                "Właściciel ma teraz więcej sklepów, niż pozwala jego plan, albo nie ma planu. Ustal z nim, co dalej."
            ))
