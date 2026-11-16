from django.conf import settings
from django.utils.module_loading import import_string

from ..platforms import Platform

# Real shops on the shop node from infra/shops, one provisioner per platform.
DOCKER_PROVISIONERS = {
    Platform.WOOCOMMERCE: "shops.platforms.woocommerce.WooCommerceProvisioner",
    Platform.PRESTASHOP: "shops.platforms.prestashop.PrestaShopProvisioner",
    Platform.MAGENTO: "shops.platforms.magento.MagentoProvisioner",
}
# What SHOP_PROVISIONER said for real shops before there were several platforms.
LEGACY_DOCKER_SETTING = "shops.provisioning.docker_provisioner.DockerProvisioner"


def get_provisioner(platform=Platform.WOOCOMMERCE):
    """
    The provisioner for shops on `platform` (a shop's `platform`). SHOP_PROVISIONER is "docker" for real shops
    (the old DockerProvisioner path from older .env files works too) or one class used for every platform,
    e.g. the simulated FakeProvisioner.
    """
    path = settings.SHOP_PROVISIONER
    if path in ("docker", LEGACY_DOCKER_SETTING):
        path = DOCKER_PROVISIONERS[Platform(platform)]
    return import_string(path)()
