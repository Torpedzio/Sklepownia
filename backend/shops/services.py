from django.conf import settings
from django.db import IntegrityError, transaction

from accounts.models import User

from .models import ProvisioningJob, ProvisioningStep, Shop, ShopConfig
from .provisioning import get_provisioner
from .tasks import provision_shop


class ShopLimitReached(Exception):
    pass


class SlugTaken(Exception):
    pass


def create_shop(owner, *, name, slug, **config):
    try:
        with transaction.atomic():
            # Lock the owner so concurrent requests can't both pass the limit check.
            User.objects.select_for_update().get(pk=owner.pk)
            live_shops = owner.shops.exclude(status=Shop.Status.DELETED).count()
            if live_shops >= settings.SHOPS_MAX_PER_USER:
                raise ShopLimitReached()
            shop = Shop.objects.create(owner=owner, name=name, slug=slug)
            ShopConfig.objects.create(shop=shop, **config)
            _enqueue_provisioning(shop)
    except IntegrityError as exc:
        if "unique_slug_for_live_shops" in str(exc):
            raise SlugTaken() from exc
        raise
    return shop


def retry_shop(shop):
    with transaction.atomic():
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        shop.transition_to(Shop.Status.PENDING)
        _enqueue_provisioning(shop)
    return shop


def delete_shop(shop):
    # Tearing down real infrastructure comes with the Docker provisioner.
    with transaction.atomic():
        shop = Shop.objects.select_for_update().get(pk=shop.pk)
        shop.transition_to(Shop.Status.DELETED)


def _enqueue_provisioning(shop):
    job = ProvisioningJob.objects.create(shop=shop)
    ProvisioningStep.objects.bulk_create(
        ProvisioningStep(job=job, key=key, label=label, order=order)
        for order, (key, label) in enumerate(get_provisioner().STEPS)
    )
    transaction.on_commit(lambda: provision_shop.delay(job.pk))
    return job
