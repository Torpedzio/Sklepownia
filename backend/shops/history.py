"""A shop's history for its owner: who did what (ShopEvent). Routine reads, like refreshing settings, stay out."""

from django.utils import formats, timezone

from .models import ShopEvent, ShopOperation
from .shop_settings import describe as describe_changes

Kind = ShopEvent.Kind
# Asked for by the app on its own, not a change anyone made.
UNRECORDED_OPERATIONS = {ShopOperation.Kind.SYNC_SETTINGS}
ORDER_KINDS = {Kind.ORDER_PAID, Kind.ORDER_SHIPPED, Kind.ORDER_CANCELLED}


def record(shop, kind, actor=None, operation=None, **data):
    return ShopEvent.objects.create(shop=shop, kind=kind, actor=actor, operation=operation, data=data)


def record_operation(operation):
    if operation.kind not in UNRECORDED_OPERATIONS:
        record(operation.shop, Kind.OPERATION, operation.requested_by, operation)


def events(shop):
    return shop.events.select_related("actor", "operation__backup")


def title(event):
    if event.kind == Kind.OPERATION and event.operation is not None:
        return event.operation.get_kind_display()
    if event.kind == Kind.INVITATION_SENT and event.data.get("again"):
        return "Ponowne zaproszenie do zespołu"
    if event.kind == Kind.MEMBER_LEFT and event.data.get("account_deleted"):
        return "Usunięcie konta i odejście z zespołu"
    return event.get_kind_display()


def detail(event):
    """What it was about, e.g. the changed settings or the invited address; empty when the title says it all."""
    operation = event.operation
    if event.kind == Kind.OPERATION and operation is not None:
        if operation.kind == ShopOperation.Kind.UPDATE_SETTINGS:
            return ", ".join(describe_changes(operation.changes))
        if operation.kind == ShopOperation.Kind.RESTORE_BACKUP and operation.backup is not None:
            return f"Kopia z {formats.date_format(timezone.localtime(operation.backup.created_at), 'j E Y, H:i')}"
        removed = operation.result.get("removed")
        if operation.kind == ShopOperation.Kind.REMOVE_SAMPLE_PRODUCTS and removed is not None:
            return f"Usunięte produkty: {removed}"
        return ""
    if event.kind == Kind.SUSPENDED:
        return "Sklep nie mieścił się w planie właściciela."
    if event.kind == Kind.RESUMED and event.actor is None:
        return "Plan właściciela ma na niego miejsce."
    if event.kind in ORDER_KINDS:
        tracking = event.data.get("tracking_number", "")
        if tracking and event.data.get("carrier"):
            tracking = f"{tracking} ({event.data['carrier']})"
        return ", ".join(filter(None, [f"Nr {event.data.get('number', '')}", f"przesyłka {tracking}" if tracking else ""]))
    if event.kind == Kind.PRODUCT_STOCK:
        before, after = event.data.get("before"), event.data.get("after")
        count = f"{'bez liczenia' if before is None else before} → {after} szt."
        return f"{event.data.get('name', '')}: {count}"
    if event.kind == Kind.PRODUCT_UPDATED:
        return ": ".join(filter(None, [event.data.get("name", ""), ", ".join(event.data.get("fields", []))]))
    if event.kind in (Kind.PRODUCT_CREATED, Kind.PRODUCT_DELETED):
        return event.data.get("name", "")
    if event.kind == Kind.MEMBER_REMOVED:
        return event.data.get("name") or event.data.get("email", "")
    return event.data.get("email", "")
