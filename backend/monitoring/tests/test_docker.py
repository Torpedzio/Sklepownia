"""How the Docker provisioners see a shop's health (shops/provisioning/container.py), with a mocked Docker client."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from docker.errors import DockerException, NotFound
from docker.types.containers import ContainerConfig

from accounts.models import User
from shops.models import Shop
from shops.platforms.woocommerce import WooCommerceProvisioner
from shops.provisioning import container as container_module
from shops.provisioning.base import ContainerState, PageCheck, ProvisioningError

pytestmark = pytest.mark.django_db


@pytest.fixture
def provisioner():
    instance = WooCommerceProvisioner()
    # cached_property: an instance attribute replaces the real Docker client.
    instance.__dict__["client"] = MagicMock()
    return instance


@pytest.fixture
def shop():
    owner = User.objects.create_user(email="wlasciciel@example.com", password="Sekretne-haslo-123")
    return Shop.objects.create(owner=owner, name="Palarnia", slug="palarnia", status=Shop.Status.ACTIVE)


@pytest.fixture
def clock(monkeypatch):
    """Time passes only when the code sleeps."""
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(container_module.time, "sleep", sleep)
    monkeypatch.setattr(container_module.time, "monotonic", lambda: now[0])
    return now


def answer(exit_code, output):
    return SimpleNamespace(exit_code=exit_code, output=output)


def container(status="running", health=None, labels=None):
    state = {"Status": status, **({"Health": {"Status": health}} if health else {})}
    return MagicMock(status=status, labels=labels or {}, attrs={"State": state})


def test_the_home_page_is_visited_through_the_proxy_like_a_customer_would(provisioner, shop):
    shop_container = provisioner.client.containers.get.return_value
    shop_container.exec_run.return_value = answer(0, b"200 0.254 ")

    assert provisioner.check_page(shop) == PageCheck(status=200, seconds=0.254)

    provisioner.client.containers.get.assert_called_with("shop-%d" % shop.pk)
    command = shop_container.exec_run.call_args.args[0]
    assert command[0] == "curl"
    assert command[command.index("-H") + 1] == "Host: palarnia.localhost"
    assert command[-1] == "http://shops-proxy/"
    assert command[command.index("-w") + 1] == "%{http_code} %{time_total} %header{X-Shop-Unavailable}"


def test_the_platforms_page_for_a_shop_the_proxy_skips_is_told_apart(provisioner, shop):
    provisioner.client.containers.get.return_value.exec_run.return_value = answer(0, b"503 0.010 opening")

    assert provisioner.check_page(shop) == PageCheck(status=503, seconds=0.01, unavailable=True)


@pytest.mark.parametrize("exit_code, reason", [
    (28, "Brak odpowiedzi w 20 s."),
    (7, "Serwer proxy nie przyjmuje połączeń."),
    (35, "curl zakończył się kodem 35"),
])
def test_no_answer_says_why(provisioner, shop, exit_code, reason):
    provisioner.client.containers.get.return_value.exec_run.return_value = answer(exit_code, b"000 20.001 ")

    assert provisioner.check_page(shop) == PageCheck(status=None, seconds=20.001, error=reason)


def test_a_shop_without_a_container_has_no_page(provisioner, shop):
    provisioner.client.containers.get.side_effect = NotFound("No such container")

    page = provisioner.check_page(shop)

    assert page.status is None
    assert page.error == "Nie da się wejść do kontenera sklepu (NotFound)."


def test_the_shops_containers_are_found_by_their_label(provisioner):
    provisioner.client.containers.list.return_value = [
        container("running", "healthy", {"shops.id": "7"}),
        container("exited", labels={"shops.id": "8"}),
        container("running", labels={"shops.id": "nie-liczba"}),
    ]

    assert provisioner.container_states() == {
        7: ContainerState("running", "healthy"), 8: ContainerState("exited"),
    }
    provisioner.client.containers.list.assert_called_once_with(all=True, filters={"label": "shops.id"})


def test_a_started_shop_is_waited_for_until_healthy_and_routed(provisioner, shop, clock, monkeypatch):
    started = container("running", "starting")
    healths = iter(["starting", "starting", "healthy"])
    started.reload.side_effect = lambda: started.attrs["State"]["Health"].update(Status=next(healths))
    provisioner.client.containers.get.return_value = started
    pages = iter([PageCheck(503, unavailable=True), PageCheck(200)])
    monkeypatch.setattr(provisioner, "check_page", lambda shop: next(pages))

    assert provisioner._wait_until_routed(shop) is True
    assert clock[0] == 3 * 2 + 1


def test_waiting_gives_up_on_a_shop_that_never_gets_healthy(provisioner, shop, clock):
    provisioner.client.containers.get.return_value = container("running", "starting")

    assert provisioner._wait_until_routed(shop, timeout=30) is False
    assert clock[0] >= 30


def test_a_container_from_before_the_healthcheck_is_routed_while_it_runs(provisioner, shop, clock):
    provisioner.client.containers.get.return_value = container("running")

    assert provisioner._wait_until_routed(shop) is True


def test_a_shop_is_started_again_from_its_files(provisioner, shop, monkeypatch):
    provisioner.client.containers.get.side_effect = NotFound("No such container")
    started = []
    monkeypatch.setattr(provisioner, "step_start_container", started.append)
    monkeypatch.setattr(provisioner, "_wait_until_routed", lambda shop: True)

    assert provisioner.start_shop(shop) is True
    assert started == [shop]
    provisioner.client.volumes.get.assert_called_once_with("shop-%d" % shop.pk)


def test_a_shop_whose_files_are_gone_is_not_started_empty(provisioner, shop, monkeypatch):
    provisioner.client.containers.get.side_effect = NotFound("No such container")
    provisioner.client.volumes.get.side_effect = NotFound("No such volume")
    monkeypatch.setattr(provisioner, "step_start_container", lambda shop: pytest.fail("started"))

    with pytest.raises(ProvisioningError, match="Nie ma kontenera ani wolumenu shop-"):
        provisioner.start_shop(shop)


def test_a_restart_waits_until_the_shop_is_routed_again(provisioner, shop, monkeypatch):
    monkeypatch.setattr(provisioner, "_wait_until_routed", lambda shop: False)

    assert provisioner.restart_shop(shop) is False
    provisioner.client.containers.get.return_value.restart.assert_called_once_with(timeout=30)


def test_the_shared_services_are_checked_by_their_containers(provisioner):
    containers = {
        "shops-proxy": container("running", "healthy"),
        "shops-db": container("exited"),
        "shops-search": container("running", "unhealthy"),
    }

    def get(name):
        if name not in containers:
            raise NotFound(name)
        return containers[name]

    provisioner.client.containers.get.side_effect = get

    problems = provisioner.service_problems(["shops-proxy", "shops-db", "shops-search", "shops-cache"], ["smtp"])

    assert problems == {
        "shops-db": "Kontener nie działa (exited).",
        "shops-search": "Kontener działa, ale nie przechodzi swojego healthchecka.",
        "shops-cache": "Nie ma takiego kontenera.",
    }


def test_without_docker_the_rest_is_unknown(provisioner):
    provisioner.client.ping.side_effect = DockerException("connection refused")

    assert provisioner.service_problems(["shops-proxy"]) == {"docker": "Docker nie odpowiada."}


def test_the_free_disk_space_is_read_where_the_shops_keep_their_data(provisioner, monkeypatch):
    calls = []

    def run(container, command, user="", environment=None):
        calls.append((container, command))
        return "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/sda1 1000 900 100 90% /var/lib/mysql"

    monkeypatch.setattr(provisioner, "_exec", run)

    assert provisioner.disk_space() == (100 * 1024, 1000 * 1024)
    assert calls == [("shops-db", ["df", "-Pk", "/var/lib/mysql"])]

    monkeypatch.setattr(provisioner, "_exec", lambda *args, **kwargs: "")
    assert provisioner.disk_space() is None


def test_the_healthcheck_reaches_docker_whole(provisioner, shop):
    """docker-py drops StartInterval by itself; without it a new shop waits 60 s for its first check."""
    healthcheck = provisioner.healthcheck(shop)

    sent = ContainerConfig("1.44", "image", None, healthcheck=healthcheck)["Healthcheck"]

    assert sent["StartInterval"] == 3_000_000_000
    assert sent["StartPeriod"] == 300_000_000_000
    assert "-H 'Host: palarnia.localhost' http://localhost/" in sent["Test"][1]
