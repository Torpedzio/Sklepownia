import logging

from django.db import transaction
from django.utils import timezone

from .. import backups, documents, shop_settings
from ..models import ShopBackup, ShopChecklist, ShopOperation, ShopSettings, ShopTemplate
from . import get_provisioner
from .base import ProvisioningError

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Nie udało się wprowadzić zmian w sklepie. Spróbuj ponownie za chwilę."
PUBLISH_ERROR = "Nie udało się opublikować regulaminu i polityki prywatności w sklepie. Spróbuj ponownie za chwilę."

Kind = ShopOperation.Kind


def run_operation(operation_id):
    """Runs a queued operation and returns it; None when it had already run."""
    with transaction.atomic():
        operation = ShopOperation.objects.select_for_update(of=("self",)).select_related("shop__config__template").get(
            pk=operation_id,
        )
        if operation.status != ShopOperation.Status.QUEUED:
            logger.info("Shop operation %s already %s, skipping", operation_id, operation.status)
            return None
        operation.status = ShopOperation.Status.RUNNING
        operation.started_at = timezone.now()
        operation.save(update_fields=["status", "started_at"])

    shop = operation.shop
    provisioner = get_provisioner(shop.platform)
    try:
        if operation.kind == Kind.UPDATE_SETTINGS:
            _update_settings(provisioner, shop, operation.changes, operation.secret_values)
        elif operation.kind == Kind.SYNC_SETTINGS:
            _sync(provisioner, shop)
            # E.g. the owner renamed the shop in its admin panel: the app shows the new name.
            _follow_settings(shop)
        elif operation.kind == Kind.RESET_ADMIN_PASSWORD:
            provisioner.reset_admin_password(shop)
        elif operation.kind == Kind.REMOVE_SAMPLE_PRODUCTS:
            operation.result = {"removed": provisioner.remove_sample_products(shop)}
            # The start checklist ticks it off at once, without counting the products again.
            ShopChecklist.objects.filter(shop=shop).update(sample_products=0)
        elif operation.kind == Kind.PUBLISH_DOCUMENTS:
            _publish_again(provisioner, shop)
        elif operation.kind == Kind.CREATE_BACKUP:
            operation.backup = backups.back_up(shop, ShopBackup.Kind.MANUAL)
        elif operation.kind == Kind.RESTORE_BACKUP:
            if operation.backup is None:
                # Removed by the nightly clean-up after the owner picked it.
                raise ProvisioningError(backups.BACKUP_GONE)
            operation.result = {"before": backups.restore(shop, operation.backup).pk}
    except Exception as exc:
        logger.exception("Shop operation %s (%s) on shop %s failed", operation.pk, operation.kind, shop.pk)
        # Raw exception text may contain internals, so the owner only sees it for known errors.
        operation.error = str(exc) if isinstance(exc, ProvisioningError) else GENERIC_ERROR
        _finish(operation, ShopOperation.Status.FAILED)
        if operation.kind == Kind.UPDATE_SETTINGS:
            # Part of the change may have been applied; show what the shop really has now.
            _sync_quietly(provisioner, shop)
        return operation
    _finish(operation, ShopOperation.Status.SUCCEEDED)
    return operation


def _update_settings(provisioner, shop, changes, keys):
    stored = _stored(shop)
    # The shop gets the payment keys; the platform keeps the settings without them.
    changes = shop_settings.reveal(changes, keys)
    values = shop_settings.merge(stored.values, changes)
    # The provisioning steps reused for language and theme read the shop's config, so it gets the new values first.
    _apply_to_shop(shop, changes)
    provisioner.apply_settings(shop, changes, values)
    if documents.should_publish(changes, values):
        _publish_documents(provisioner, shop, values)
    with transaction.atomic():
        shop.save(update_fields=["name", "updated_at"])
        shop.config.save()
        stored.values = shop_settings.conceal(values, keys)
        stored.save(update_fields=["values", "updated_at"])
    _sync_quietly(provisioner, shop)


def _publish_documents(provisioner, shop, values):
    """Publish the terms and privacy policy for `values` in the shop and store their URLs in `values`."""
    try:
        published = provisioner.publish_documents(shop, documents.render(values, shop.url))
    except Exception as exc:
        # The other changes are in the shop by now; the owner learns which part failed.
        raise ProvisioningError(PUBLISH_ERROR) from exc
    values["documents"].update(
        terms_url=published["terms"], privacy_url=published["privacy"], version=documents.VERSION,
    )


def _publish_again(provisioner, shop):
    """Republish from the current templates, e.g. after a change in the law (publish_shop_documents)."""
    stored = _stored(shop)
    values = shop_settings.complete(stored.values, shop_settings.default_settings(shop))
    if not values["documents"]["managed"]:
        return
    _publish_documents(provisioner, shop, values)
    stored.values = values
    stored.save(update_fields=["values", "updated_at"])


def _apply_to_shop(shop, changes):
    general = changes.get("general", {})
    region = changes.get("region", {})
    config = shop.config
    if "name" in general:
        shop.name = general["name"]
    if "description" in general:
        config.description = general["description"]
    if "contact_email" in general:
        config.contact_email = general["contact_email"]
    for field in ("language", "currency", "country"):
        if field in region:
            setattr(config, field, region[field])
    if "theme" in changes.get("appearance", {}):
        config.template = ShopTemplate.objects.get(slug=changes["appearance"]["theme"])


def read_back(shop):
    """For a shop changed outside these operations (restored backup): re-read settings, republish documents."""
    provisioner = get_provisioner(shop.platform)
    _sync_quietly(provisioner, shop)
    _follow_settings(shop)
    try:
        _publish_again(provisioner, shop)
    except Exception:
        logger.exception("Publishing the documents of shop %s again failed", shop.pk)


def _follow_settings(shop):
    """Copy what the shop has now (name, language, theme...) into its own fields; after a restore, the backup's."""
    values = _stored(shop).values
    changes = {"general": values["general"], "region": values["region"]}
    # Only a theme of the shop's platform: Shop.config.template is what the shop is set up with again.
    theme = ShopTemplate.objects.filter(slug=values["appearance"]["theme"], platform=shop.platform).first()
    if theme is not None:
        changes["appearance"] = {"theme": theme.slug}
    before = _own_fields(shop)
    _apply_to_shop(shop, changes)
    if _own_fields(shop) == before:
        return
    with transaction.atomic():
        shop.save(update_fields=["name", "updated_at"])
        shop.config.save()


def _own_fields(shop):
    config = shop.config
    return (
        shop.name, config.description, config.contact_email, config.language, config.currency, config.country,
        config.template_id,
    )


def _sync(provisioner, shop):
    stored = _stored(shop)
    values = provisioner.read_settings(shop)
    stored.values = shop_settings.complete(values, stored.values)
    stored.synced_at = timezone.now()
    stored.save(update_fields=["values", "synced_at", "updated_at"])


def _sync_quietly(provisioner, shop):
    try:
        _sync(provisioner, shop)
    except Exception:
        logger.exception("Reading the settings of shop %s failed", shop.pk)


def _stored(shop):
    stored, _ = ShopSettings.objects.get_or_create(shop=shop, defaults={"values": shop_settings.default_settings(shop)})
    return stored


def _finish(operation, status):
    operation.status = status
    operation.finished_at = timezone.now()
    # Applied or not, the keys are gone: a failed change is typed again.
    operation.secrets = ""
    operation.save(update_fields=["status", "error", "result", "backup", "secrets", "finished_at"])
