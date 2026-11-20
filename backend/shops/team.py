"""Who runs a shop: its owner (Shop.owner, who pays for the plan) and the staff (ShopMember)."""

from django.db.models import Case, CharField, Q, Value, When
from rest_framework.permissions import BasePermission

from .models import Shop, ShopMember

Role = ShopMember.Role
OWNER_ONLY = "Tylko właściciel sklepu może to zrobić."


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
