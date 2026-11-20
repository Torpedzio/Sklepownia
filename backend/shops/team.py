"""Who runs a shop: its owner (Shop.owner, who pays for the plan) and the staff (ShopMember), invited by e-mail."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Case, CharField, Q, Value, When
from django.utils import timezone
from rest_framework.permissions import BasePermission

from .models import Shop, ShopInvitation, ShopMember

Role = ShopMember.Role
OWNER_ONLY = "Tylko właściciel sklepu może to zrobić."


class TeamError(Exception):
    """The message is for the person who asked; `conflict` when the request was fine but the team's state isn't."""

    def __init__(self, message, conflict=False):
        super().__init__(message)
        self.conflict = conflict


def visible_shops(user):
    """Shops the user owns or serves, each annotated with the user's `role`."""
    served = ShopMember.objects.filter(user=user).values("shop")
    return Shop.objects.filter(Q(owner=user) | Q(pk__in=served)).annotate(
        role=Case(When(owner=user, then=Value(Role.OWNER)), default=Value(Role.STAFF), output_field=CharField()),
    )


class StaffActions(BasePermission):
    """The staff may only do the view's STAFF_ACTIONS in a shop; everything else is the owner's."""

    message = OWNER_ONLY

    def has_object_permission(self, request, view, shop):
        return shop.owner_id == request.user.pk or view.action in view.STAFF_ACTIONS


def staff_limit(shop):
    """Staff the owner's plan allows in the shop, None for no limit; 0 without a plan."""
    from .services import active_plan

    plan = active_plan(shop.owner)
    return 0 if plan is None else plan.max_staff


def pending_invitations(shop):
    return shop.invitations.filter(expires_at__gt=timezone.now())


def overview(shop):
    """For TeamSerializer; expired invitations stay on the list so the owner can send them again."""
    members = list(shop.members.select_related("user").order_by("created_at"))
    pending = pending_invitations(shop).count()
    return {
        "owner": shop.owner,
        "members": members,
        "invitations": shop.invitations.order_by("-created_at"),
        "limit": staff_limit(shop),
        "used": len(members) + pending,
    }


def invite(shop, email, invited_by):
    """Invites `email`, or invites it again with a new term; the e-mail goes out after the commit."""
    from .tasks import send_invitation_email

    email = email.strip().lower()
    with transaction.atomic():
        # One invitation at a time per shop, so two can't both take the last place.
        shop = Shop.objects.select_for_update().select_related("owner").get(pk=shop.pk)
        if email == shop.owner.email:
            raise TeamError("To Twój adres: właściciel jest w zespole od początku.")
        if shop.members.filter(user__email=email).exists():
            raise TeamError("Ta osoba jest już w zespole sklepu.")
        limit = staff_limit(shop)
        if limit is not None:
            taken = shop.members.count() + pending_invitations(shop).exclude(email=email).count()
            if taken >= limit:
                raise TeamError(_full(limit), conflict=True)
        invitation, _ = ShopInvitation.objects.update_or_create(
            shop=shop, email=email,
            defaults={"invited_by": invited_by, "expires_at": timezone.now() + timedelta(days=ShopInvitation.VALID_DAYS)},
        )
        transaction.on_commit(lambda: send_invitation_email.delay(invitation.pk))
    return invitation


def invitations_for(user):
    """Unexpired invitations to the user's verified address, to shops that still exist."""
    if not user.is_email_verified:
        return ShopInvitation.objects.none()
    return (
        ShopInvitation.objects.filter(email=user.email, expires_at__gt=timezone.now())
        .exclude(shop__status=Shop.Status.DELETED)
        .select_related("shop", "invited_by")
        .order_by("-created_at")
    )


def accept(invitation, user):
    """`invitation` from invitations_for(user). Returns the shop."""
    with transaction.atomic():
        shop = Shop.objects.select_for_update().get(pk=invitation.shop_id)
        if shop.owner_id == user.pk or shop.members.filter(user=user).exists():
            invitation.delete()
            return shop
        limit = staff_limit(shop)
        # The plan may have changed since the invitation was sent.
        if limit is not None and shop.members.count() >= limit:
            raise TeamError("Zespół sklepu jest już pełny. Poproś właściciela o miejsce.", conflict=True)
        ShopMember.objects.create(shop=shop, user=user)
        invitation.delete()
    return shop


def leave(shop, user):
    if shop.owner_id == user.pk:
        raise TeamError("Właściciel nie może opuścić swojego sklepu. Możesz go usunąć.", conflict=True)
    ShopMember.objects.filter(shop=shop, user=user).delete()


def _full(limit):
    return (
        f"Twój plan pozwala na {limit} {_people(limit)} z obsługi w sklepie, licząc wysłane zaproszenia. "
        "Usuń kogoś z zespołu albo zmień plan."
    )


def _people(count):
    if count == 1:
        return "osobę"
    return "osoby" if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else "osób"
