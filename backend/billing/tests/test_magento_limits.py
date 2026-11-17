"""Magento needs about three times the memory of other shops, so plans allow only a few: none in Start,
1 of 3 shops in Standard, 5 of 10 in Biznes."""

from datetime import timedelta

import pytest
from django.utils import timezone

from billing.models import Plan, Subscription
from shops.models import ProvisioningJob, Shop, ShopConfig, ShopTemplate
from shops.platforms import Platform

pytestmark = pytest.mark.django_db

RETURN_URL = "http://localhost:8081/billing/return"
NOT_IN_START = "Sklepy Magento są w planach Standard i Biznes. Plan Start ich nie obejmuje."


@pytest.fixture
def plans(plan):
    return {code: Plan.objects.get(code=code) for code in ("start", "standard", "business")}


def on_plan(user, plan):
    now = timezone.now()
    Subscription.objects.filter(user=user).update(
        plan=plan, current_period_start=now - timedelta(days=15), current_period_end=now + timedelta(days=15),
    )


def make_shop(user, name, platform=Platform.WOOCOMMERCE, status=Shop.Status.ACTIVE, age_days=30):
    template = {Platform.WOOCOMMERCE: "storefront", Platform.MAGENTO: "luma"}[platform]
    shop = Shop.objects.create(owner=user, name=name, slug=name.lower(), status=status, platform=platform)
    Shop.objects.filter(pk=shop.pk).update(created_at=timezone.now() - timedelta(days=age_days))
    ShopConfig.objects.create(shop=shop, industry="food", template=ShopTemplate.objects.get(slug=template),
                              category_count=3, contact_email="kontakt@example.com")
    ProvisioningJob.objects.create(shop=shop, status=ProvisioningJob.Status.SUCCEEDED)
    return shop


def create_magento(client, captured, slug="magento"):
    with captured(execute=True):
        return client.post("/api/shops/", {
            "name": "Sklep", "slug": slug, "industry": "fashion", "platform": "magento", "template": "luma",
        }, format="json")


def test_plans_say_how_many_magento_shops_they_allow(api_client, plans):
    data = api_client.get("/api/billing/plans/").data

    assert [(p["code"], p["max_shops"], p["max_magento_shops"]) for p in data] == [
        ("start", 1, 0), ("standard", 3, 1), ("business", 10, 5),
    ]
    assert "W tym 1 sklep na Magento" in data[1]["features"]


# --- creating ---


def test_standard_allows_one_magento_shop(auth_client, verified_user, plans, django_capture_on_commit_callbacks):
    assert create_magento(auth_client, django_capture_on_commit_callbacks).status_code == 201

    response = create_magento(auth_client, django_capture_on_commit_callbacks, slug="drugi")

    assert response.status_code == 400
    assert response.data["platform"] == [
        "Masz już 1 sklep Magento, tyle ile pozwala plan Standard. Usuń go albo przejdź na plan Biznes.",
    ]
    # Other systems still fit in the plan.
    make_shop(verified_user, "Kawiarnia")
    assert auth_client.get("/api/auth/me/").data["can_create_shops"] is True


def test_start_has_no_magento(auth_client, verified_user, plans, django_capture_on_commit_callbacks):
    on_plan(verified_user, plans["start"])

    response = create_magento(auth_client, django_capture_on_commit_callbacks)

    assert response.status_code == 400
    assert response.data["platform"] == [NOT_IN_START]
    assert not Shop.objects.exists()


def test_deleted_and_suspended_magento_shops_free_the_place(auth_client, verified_user, plans,
                                                            django_capture_on_commit_callbacks):
    make_shop(verified_user, "Usuniety", Platform.MAGENTO, status=Shop.Status.DELETED)
    make_shop(verified_user, "Zawieszony", Platform.MAGENTO, status=Shop.Status.SUSPENDED)

    assert create_magento(auth_client, django_capture_on_commit_callbacks).status_code == 201


# --- the form ---


def platforms(client):
    return {p["value"]: (p["available"], p["note"]) for p in client.get("/api/shops/form-options/").data["platforms"]}


def test_the_form_says_when_magento_is_not_in_the_plan(auth_client, verified_user, plans):
    assert platforms(auth_client)["magento"] == (True, "")

    on_plan(verified_user, plans["start"])
    assert platforms(auth_client) == {
        "woocommerce": (True, ""), "prestashop": (True, ""), "magento": (False, NOT_IN_START),
    }

    on_plan(verified_user, plans["standard"])
    make_shop(verified_user, "Duzy", Platform.MAGENTO)
    assert platforms(auth_client)["magento"] == (
        False, "Masz już 1 sklep Magento, tyle ile pozwala plan Standard. Usuń go albo przejdź na plan Biznes.",
    )


def test_without_a_plan_the_form_says_which_plans_have_magento(api_client, unsubscribed_user, plans):
    api_client.force_authenticate(unsubscribed_user)

    assert platforms(api_client) == {
        "woocommerce": (True, ""), "prestashop": (True, ""), "magento": (True, "W planach Standard i Biznes."),
    }


# --- changing plans and resuming ---


def preview(client, plan, **data):
    return client.post("/api/billing/subscription/change-preview/", {"plan": plan, **data}, format="json").data


def test_a_smaller_plan_keeps_the_oldest_shops_that_fit(auth_client, verified_user, plans,
                                                       django_capture_on_commit_callbacks):
    on_plan(verified_user, plans["business"])
    first = make_shop(verified_user, "Pierwszy", Platform.MAGENTO, age_days=30)
    second = make_shop(verified_user, "Drugi", Platform.MAGENTO, age_days=20)
    cafe = make_shop(verified_user, "Kawiarnia", age_days=10)

    data = preview(auth_client, "standard")

    assert data["blocked"] == ""
    assert [shop["name"] for shop in data["keep"]] == ["Pierwszy", "Kawiarnia"]
    assert [(shop["name"], shop["platform_display"]) for shop in data["suspend"]] == [("Drugi", "Magento")]

    # Into Start only the WooCommerce shop fits, though both Magento shops are older.
    data = preview(auth_client, "start")
    assert [shop["name"] for shop in data["keep"]] == ["Kawiarnia"]

    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post("/api/billing/subscription/change/",
                         {"plan": "standard", "return_url": RETURN_URL}, format="json")
    statuses = dict(Shop.objects.filter(pk__in=[first.pk, second.pk, cafe.pk]).values_list("name", "status"))
    assert statuses == {"Pierwszy": "active", "Drugi": "suspended", "Kawiarnia": "active"}


def test_keeping_too_many_magento_shops_is_refused(auth_client, verified_user, plans):
    on_plan(verified_user, plans["business"])
    shops = [make_shop(verified_user, name, Platform.MAGENTO) for name in ("Pierwszy", "Drugi")]
    make_shop(verified_user, "Kawiarnia")
    make_shop(verified_user, "Herbaciarnia")

    data = preview(auth_client, "standard", keep_shops=[shop.pk for shop in shops])
    assert data["blocked"] == "W planie Standard zostawisz najwyżej 1 sklep Magento."

    data = preview(auth_client, "start", keep_shops=[shops[0].pk])
    assert data["blocked"] == "Plan Start nie obejmuje sklepów Magento."


def test_suspended_magento_shops_come_back_only_within_the_limit(auth_client, verified_user, plans,
                                                                django_capture_on_commit_callbacks):
    make_shop(verified_user, "Aktywny", Platform.MAGENTO)
    suspended = make_shop(verified_user, "Zawieszony", Platform.MAGENTO, status=Shop.Status.SUSPENDED)

    # Standard has room for 3 shops but only 1 on Magento.
    response = auth_client.post(f"/api/shops/{suspended.pk}/resume/")
    assert response.status_code == 400
    assert response.data["detail"] == (
        "Masz już 1 sklep Magento, tyle ile pozwala plan Standard. "
        "Usuń inny sklep Magento albo zmień plan, żeby przywrócić ten."
    )

    assert [shop["name"] for shop in preview(auth_client, "business")["resume"]] == ["Zawieszony"]
