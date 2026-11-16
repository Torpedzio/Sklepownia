from django.conf import settings
from django.utils.module_loading import import_string

from ..platforms import Platform

# Real shops on the shop node from infra/shops, one provisioner per platform.
DOCKER_PROVISIONERS = {
    Platform.WOOCOMMERCE: "shops.provisioning.docker_provisioner.DockerProvisioner",
    Platform.PRESTASHOP: "shops.provisioning.prestashop.PrestaShopProvisioner",
}


def get_provisioner(platform=Platform.WOOCOMMERCE):
    """
    The provisioner for shops on `platform` (a shop's `platform`). SHOP_PROVISIONER is "docker" for real shops
    (the WooCommerce class path works too, as in older .env files) or one class used for every platform,
    e.g. the simulated FakeProvisioner.
    """
    path = settings.SHOP_PROVISIONER
    if path in ("docker", DOCKER_PROVISIONERS[Platform.WOOCOMMERCE]):
        path = DOCKER_PROVISIONERS[Platform(platform)]
    return import_string(path)()
