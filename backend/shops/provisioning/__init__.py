from django.conf import settings
from django.utils.module_loading import import_string

from ..platforms import Platform

DOCKER_PROVISIONERS = {
    Platform.WOOCOMMERCE: "shops.platforms.woocommerce.WooCommerceProvisioner",
    Platform.PRESTASHOP: "shops.platforms.prestashop.PrestaShopProvisioner",
    Platform.MAGENTO: "shops.platforms.magento.MagentoProvisioner",
}
# SHOP_PROVISIONER value for real shops from older .env files.
LEGACY_DOCKER_SETTING = "shops.provisioning.docker_provisioner.DockerProvisioner"


def get_provisioner(platform=Platform.WOOCOMMERCE):
    """SHOP_PROVISIONER is "docker" (or the legacy path) for real shops, or one class for every platform (e.g. fake)."""
    path = settings.SHOP_PROVISIONER
    if path in ("docker", LEGACY_DOCKER_SETTING):
        path = DOCKER_PROVISIONERS[Platform(platform)]
    return import_string(path)()
