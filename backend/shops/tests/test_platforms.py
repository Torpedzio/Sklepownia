"""Shops on platforms other than WooCommerce, through the API with the simulated provisioner."""

import pytest

from shops.models import ProvisioningStep, Shop, ShopCredentials
from shops.platforms import Platform, platform_info
from shops.provisioning import get_provisioner
from shops.platforms.woocommerce import WooCommerceProvisioner
from shops.provisioning.fake import FakeProvisioner
from shops.platforms.magento import MagentoProvisioner
from shops.platforms.prestashop import PrestaShopProvisioner

pytestmark = pytest.mark.django_db


def create(client, captured, **overrides):
    payload = {"name": "Mój Sklep", "slug": "moj-sklep", "industry": "fashion", "template": "hummingbird", **overrides}
    with captured(execute=True):
        return client.post("/api/shops/", payload, format="json")


@pytest.fixture
def presta(auth_client, django_capture_on_commit_callbacks):
    return Shop.objects.get(pk=create(auth_client, django_capture_on_commit_callbacks).data["id"])


def test_the_template_decides_the_platform(auth_client, verified_user, django_capture_on_commit_callbacks):
    response = create(auth_client, django_capture_on_commit_callbacks)

    assert response.status_code == 201
    assert response.data["platform"] == "prestashop"
    assert response.data["platform_display"] == "PrestaShop"
    assert response.data["panel_name"] == "panel PrestaShop"
    shop = Shop.objects.get(pk=response.data["id"])
    keys = list(ProvisioningStep.objects.filter(job__shop=shop).values_list("key", flat=True))
    assert keys == [key for key, _ in platform_info(Platform.PRESTASHOP).steps]
    assert shop.status == Shop.Status.ACTIVE
    # PrestaShop signs in with an e-mail and has its panel in a folder of its own.
    assert ShopCredentials.objects.get(shop=shop).admin_login == verified_user.email
    assert shop.admin_url == f"{shop.url}/admin-demo/"


def test_template_of_another_platform_is_rejected(auth_client, django_capture_on_commit_callbacks):
    response = create(auth_client, django_capture_on_commit_callbacks, platform="woocommerce")

    assert response.status_code == 400
    assert "template" in response.data
    assert not Shop.objects.exists()


def test_woocommerce_shops_keep_their_panel(auth_client, django_capture_on_commit_callbacks):
    response = create(auth_client, django_capture_on_commit_callbacks, template="storefront", platform="woocommerce")

    shop = Shop.objects.get(pk=response.data["id"])
    assert shop.platform == Platform.WOOCOMMERCE
    assert shop.admin_url == f"{shop.url}/wp-admin/"


def test_panel_waits_for_the_installation(verified_user):
    shop = Shop.objects.create(owner=verified_user, name="X", slug="xyz", platform="prestashop", status="active")

    assert shop.admin_url is None


def test_settings_list_what_the_platform_supports(auth_client, presta):
    data = auth_client.get(f"/api/shops/{presta.pk}/settings/").data

    assert data["sections"] == ["general", "availability", "payments", "appearance", "documents"]
    assert [theme["value"] for theme in data["options"]["themes"]] == ["hummingbird", "classic"]
    assert data["values"]["appearance"]["theme"] == "hummingbird"


@pytest.mark.parametrize(("data", "section"), [
    ({"shipping": {"courier_enabled": True}}, "shipping"),
    ({"region": {"currency": "EUR"}}, "region"),
    ({"appearance": {"theme": "storefront"}}, "appearance"),
])
def test_settings_the_platform_lacks_are_rejected(auth_client, presta, data, section):
    response = auth_client.patch(f"/api/shops/{presta.pk}/settings/", data, format="json")

    assert response.status_code == 400
    assert section in response.data


def test_supported_settings_change(auth_client, presta, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.patch(f"/api/shops/{presta.pk}/settings/", {
            "availability": {"is_open": False}, "appearance": {"theme": "classic"},
        }, format="json")

    assert response.status_code == 202
    presta.config.refresh_from_db()
    assert presta.config.template.slug == "classic"


def test_each_platform_gets_its_provisioner(settings):
    settings.SHOP_PROVISIONER = "docker"
    assert isinstance(get_provisioner("woocommerce"), WooCommerceProvisioner)
    assert isinstance(get_provisioner("prestashop"), PrestaShopProvisioner)
    assert isinstance(get_provisioner("magento"), MagentoProvisioner)
    # The class path from older .env files means the same.
    settings.SHOP_PROVISIONER = "shops.provisioning.docker_provisioner.DockerProvisioner"
    assert isinstance(get_provisioner("prestashop"), PrestaShopProvisioner)
    # The simulation serves every platform.
    settings.SHOP_PROVISIONER = "shops.provisioning.fake.FakeProvisioner"
    assert isinstance(get_provisioner("prestashop"), FakeProvisioner)
