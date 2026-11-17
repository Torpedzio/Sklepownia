"""
The billing cycle. The gateway takes the first payment and saves the card; renewals are charged by the platform
(Tpay has no built-in subscriptions). A payment's outcome may arrive more than once, from a notification and from
asking the gateway, so applying it is idempotent.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .gateways import get_gateway
from .gateways.base import GatewayError, Payer, PaymentResult
from .models import BillingProfile, Payment, Plan, Subscription

logger = logging.getLogger(__name__)

# After a failed renewal, try again after these many days; then the plan expires.
RETRY_AFTER_DAYS = (1, 3, 5)
# A first payment nobody finished within this time is given up on.
PENDING_EXPIRES_AFTER = timedelta(days=1)
# How often a pending payment may be checked with the gateway when the owner waits on the return screen.
CHECK_INTERVAL = timedelta(seconds=5)
GATEWAY_UNAVAILABLE = "Nie udało się połączyć z operatorem płatności. Spróbuj ponownie za chwilę."


class BillingError(Exception):
    """A request the owner can fix; the message says how."""


class ProfileMissing(BillingError):
    pass


class AlreadySubscribed(BillingError):
    pass


def payer_for(user):
    profile = BillingProfile.objects.filter(user=user).first()
    if profile is None:
        return Payer(email=user.email, name=user.get_full_name() or user.email)
    return Payer(
        email=user.email,
        name=profile.payer_name,
        street=profile.street,
        postal_code=profile.postal_code,
        city=profile.city,
        country=profile.country,
        tax_id=profile.tax_id if profile.kind == BillingProfile.Kind.COMPANY else "",
    )


def start_checkout(user, plan, *, return_url, site_url, immediate_start_consent):
    """Creates the first payment for `plan` and starts it on the gateway. Returns the payment."""
    try:
        profile = user.billing_profile
    except BillingProfile.DoesNotExist:
        raise ProfileMissing("Uzupełnij dane do faktury.") from None
    if profile.kind == BillingProfile.Kind.INDIVIDUAL and not immediate_start_consent:
        raise BillingError("Potrzebna jest zgoda na rozpoczęcie usługi przed upływem 14 dni.")

    now = timezone.now()
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().filter(user=user).first()
        if subscription and subscription.status in (Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE):
            raise AlreadySubscribed("Masz już aktywny plan.")
        if subscription is None:
            subscription = Subscription(user=user, plan=plan)
        subscription.plan = plan
        subscription.status = Subscription.Status.INCOMPLETE
        subscription.terms_accepted_at = now
        subscription.immediate_start_consent_at = now if immediate_start_consent else None
        subscription.save()
        payment = Payment.objects.create(
            user=user,
            subscription=subscription,
            plan=plan,
            kind=Payment.Kind.INITIAL,
            amount=plan.price,
            currency=plan.currency,
            gateway=get_gateway().name,
            billing_details=profile.snapshot(),
        )
        # The return screen needs to know which payment it waits for.
        payment.return_url = _with_payment(return_url, payment.pk)
        payment.save(update_fields=["return_url"])

    try:
        checkout = get_gateway().start_payment(
            payment, payer_for(user), return_url=payment.return_url, site_url=site_url,
        )
    except GatewayError:
        logger.exception("Starting payment %s failed", payment.pk)
        _fail(payment, GATEWAY_UNAVAILABLE)
        raise BillingError(GATEWAY_UNAVAILABLE) from None
    payment.gateway_id = checkout.gateway_id
    payment.gateway_title = checkout.title
    payment.redirect_url = checkout.redirect_url
    payment.save(update_fields=["gateway_id", "gateway_title", "redirect_url"])
    return payment


def apply_result(result: PaymentResult):
    """Applies what the gateway says about a payment. Safe to call again with the same result."""
    payment_id = result.reference.removeprefix("payment-")
    if not payment_id.isdigit():
        logger.warning("Payment result for an unknown reference %r", result.reference)
        return None
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("subscription", "plan").filter(
            pk=payment_id,
        ).first()
        if payment is None:
            logger.warning("Payment result for a missing payment %s", payment_id)
            return None
        if payment.status != Payment.Status.PENDING or result.paid is None:
            return payment
        if result.paid and result.amount is not None and result.amount < payment.amount:
            logger.error("Payment %s paid %s instead of %s", payment.pk, result.amount, payment.amount)
            _fail(payment, "Zapłacona kwota nie zgadza się z ceną planu.")
        elif result.paid:
            _complete(payment, result)
        else:
            _fail(payment, result.error or "Płatność nie została zrealizowana.")
    _notify(payment)
    return payment


def check_with_gateway(payment):
    """
    Asks the gateway about a pending payment, at most every few seconds. Covers notifications that can't
    reach the platform, e.g. a local backend behind a home router.
    """
    now = timezone.now()
    if payment.status != Payment.Status.PENDING or (payment.checked_at and now - payment.checked_at < CHECK_INTERVAL):
        return payment
    Payment.objects.filter(pk=payment.pk).update(checked_at=now)
    try:
        result = get_gateway().fetch_result(payment)
    except GatewayError:
        logger.warning("Checking payment %s with the gateway failed", payment.pk, exc_info=True)
        return payment
    if result is not None:
        apply_result(result)
    payment.refresh_from_db()
    return payment


def reconcile_pending():
    """
    Run regularly (Celery beat). Asks the gateway about payments still pending, for when its notification never
    arrived and the payer never came back to the app; gives up on payments nobody finished within a day.
    """
    now = timezone.now()
    for payment in Payment.objects.filter(status=Payment.Status.PENDING).exclude(gateway_id="").order_by("pk"):
        try:
            check_with_gateway(payment)
        except Exception:
            logger.exception("Checking pending payment %s failed", payment.pk)
    stale = Payment.objects.filter(status=Payment.Status.PENDING, created_at__lt=now - PENDING_EXPIRES_AFTER)
    for payment_id in stale.values_list("pk", flat=True):
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment_id)
            if payment.status == Payment.Status.PENDING:
                _fail(payment, "Płatność nie została dokończona.")
        _notify(payment)


def latest_pending(user):
    """The user's most recent payment still waiting for its outcome, checked with the gateway."""
    payment = Payment.objects.filter(user=user, status=Payment.Status.PENDING).exclude(gateway_id="").first()
    return check_with_gateway(payment) if payment else None


def cancel(subscription):
    """The plan works until the period ends and then isn't renewed."""
    if subscription.status not in (Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE):
        raise BillingError("Nie ma aktywnego planu do anulowania.")
    subscription.cancel_at_period_end = True
    subscription.save(update_fields=["cancel_at_period_end", "updated_at"])


def resume(subscription):
    if subscription.status != Subscription.Status.ACTIVE or not subscription.cancel_at_period_end:
        raise BillingError("Plan nie jest anulowany.")
    subscription.cancel_at_period_end = False
    subscription.save(update_fields=["cancel_at_period_end", "updated_at"])


def renew_due():
    """
    Run regularly (Celery beat). Charges the saved card of plans whose period has ended, retries failed
    renewals, and ends plans that were cancelled or couldn't be paid.
    """
    now = timezone.now()
    due = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE, current_period_end__lte=now,
    ) | Subscription.objects.filter(status=Subscription.Status.PAST_DUE, next_attempt_at__lte=now)
    for subscription_id in due.values_list("pk", flat=True):
        try:
            renew(subscription_id)
        except Exception:
            logger.exception("Renewing subscription %s failed", subscription_id)


def renew(subscription_id):
    now = timezone.now()
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().select_related("plan", "user").get(pk=subscription_id)
        due = (
            subscription.status == Subscription.Status.ACTIVE and subscription.current_period_end <= now
        ) or (subscription.status == Subscription.Status.PAST_DUE and subscription.next_attempt_at <= now)
        if not due:
            return None
        if subscription.cancel_at_period_end:
            _end(subscription, Subscription.Status.CANCELED)
            return None
        # A renewal still waiting for the gateway is not charged twice.
        if subscription.payments.filter(kind=Payment.Kind.RENEWAL, status=Payment.Status.PENDING).exists():
            return None
        plan = subscription.plan
        # The balance (e.g. from a cheaper plan chosen mid-period) pays first.
        credit_used = min(subscription.credit, plan.price)
        amount = plan.price - credit_used
        if amount and not subscription.card_token:
            _end(subscription, Subscription.Status.EXPIRED)
            return None
        payment = Payment.objects.create(
            user=subscription.user,
            subscription=subscription,
            plan=plan,
            kind=Payment.Kind.RENEWAL,
            amount=amount,
            credit_used=credit_used,
            currency=plan.currency,
            gateway=get_gateway().name if amount else "credit",
            billing_details=_billing_details(subscription.user),
        )
    if not amount:
        return apply_result(PaymentResult(reference=payment.reference, paid=True, amount=Decimal("0")))
    try:
        result = get_gateway().charge_saved_card(payment, payer_for(subscription.user), subscription.card_token)
    except GatewayError:
        logger.exception("Charging the saved card for payment %s failed", payment.pk)
        result = PaymentResult(reference=payment.reference, paid=False, error=GATEWAY_UNAVAILABLE)
    if result.gateway_id or result.title:
        Payment.objects.filter(pk=payment.pk).update(gateway_id=result.gateway_id, gateway_title=result.title)
    return apply_result(result)


# --- applying outcomes; callers hold the payment row lock ---


def _complete(payment, result):
    now = timezone.now()
    subscription = Subscription.objects.select_for_update().select_related("plan").get(pk=payment.subscription_id)
    if payment.kind == Payment.Kind.UPGRADE:
        _complete_upgrade(payment, subscription, result, now)
        return
    months = relativedelta(months=payment.plan.interval_months)
    if payment.kind == Payment.Kind.RENEWAL and subscription.current_period_end:
        # Renewals continue the previous period, also when they were paid a few days late.
        start = subscription.current_period_end
        end = start + months
        if end <= now:
            start, end = now, now + months
    else:
        start, end = now, now + months
    subscription.status = Subscription.Status.ACTIVE
    subscription.plan = payment.plan
    subscription.current_period_start = start
    subscription.current_period_end = end
    subscription.failed_attempts = 0
    subscription.next_attempt_at = None
    subscription.credit -= payment.credit_used
    if payment.kind == Payment.Kind.INITIAL:
        subscription.cancel_at_period_end = False
    _save_card(subscription, result)
    subscription.save()
    _mark_paid(payment, result, now, start, end)


def _complete_upgrade(payment, subscription, result, now):
    """The surcharge for a better plan is paid: the plan changes now, the billing date stays."""
    old_plan = subscription.plan
    subscription.plan = payment.plan
    subscription.credit -= payment.credit_used
    subscription.cancel_at_period_end = False
    _save_card(subscription, result)
    subscription.save()
    _mark_paid(payment, result, now, now, subscription.current_period_end)
    transaction.on_commit(lambda: _after_plan_change(subscription.pk, old_plan.pk, payment.amount, Decimal("0"), []))


def _save_card(subscription, result):
    if result.card and result.card.token:
        subscription.card_token = result.card.token
        subscription.card_brand = result.card.brand
        subscription.card_tail = result.card.tail
        subscription.card_expiry = result.card.expiry


def _mark_paid(payment, result, now, start, end):
    payment.status = Payment.Status.PAID
    payment.paid_at = now
    payment.period_start = start
    payment.period_end = end
    if result.title:
        payment.gateway_title = result.title
    payment.error = ""
    payment.save()


def _fail(payment, error):
    payment.status = Payment.Status.FAILED
    payment.error = error[:300]
    payment.save(update_fields=["status", "error"])
    if payment.kind != Payment.Kind.RENEWAL:
        return
    subscription = Subscription.objects.select_for_update().get(pk=payment.subscription_id)
    subscription.failed_attempts += 1
    if subscription.failed_attempts > len(RETRY_AFTER_DAYS):
        _end(subscription, Subscription.Status.EXPIRED)
        return
    subscription.status = Subscription.Status.PAST_DUE
    subscription.next_attempt_at = timezone.now() + timedelta(days=RETRY_AFTER_DAYS[subscription.failed_attempts - 1])
    subscription.save(update_fields=["status", "failed_attempts", "next_attempt_at", "updated_at"])


def _end(subscription, status):
    subscription.status = status
    subscription.next_attempt_at = None
    subscription.save(update_fields=["status", "next_attempt_at", "updated_at"])
    transaction.on_commit(lambda: _send("ended", subscription.pk))


def _notify(payment):
    if payment.kind == Payment.Kind.UPGRADE:
        # A paid upgrade is announced as a plan change (_after_plan_change); a failed one is shown on screen.
        return
    if payment.status == Payment.Status.PAID:
        transaction.on_commit(lambda: _send("paid", payment.pk))
    elif payment.status == Payment.Status.FAILED and payment.kind == Payment.Kind.RENEWAL:
        # After the last attempt the plan has ended, and that e-mail says so; "we'll try again" would be wrong.
        retrying = Subscription.objects.filter(pk=payment.subscription_id, status=Subscription.Status.PAST_DUE)
        if retrying.exists():
            transaction.on_commit(lambda: _send("renewal_failed", payment.pk))


def _send(kind, object_id, context=None):
    from .tasks import send_billing_email

    send_billing_email.delay(kind, object_id, context or {})


def _billing_details(user):
    profile = BillingProfile.objects.filter(user=user).first()
    return profile.snapshot() if profile else {}


def default_plan():
    return Plan.objects.filter(is_active=True).first()


def _with_payment(url, payment_id):
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}payment={payment_id}"


def allowed_return_url(url):
    return any(url.startswith(prefix) for prefix in settings.BILLING_RETURN_URL_PREFIXES)


# --- changing plans ---

# A surcharge for a better plan below this is not charged: the plan just changes.
MIN_SURCHARGE = Decimal("5.00")
CENT = Decimal("0.01")


@dataclass
class PlanChange:
    """What moving to `plan` means now: money and shops. `blocked` says why it can't happen."""

    plan: Plan
    direction: str = ""
    surcharge: Decimal = Decimal("0")
    credit_used: Decimal = Decimal("0")
    amount_due: Decimal = Decimal("0")
    waived: bool = False
    credit_added: Decimal = Decimal("0")
    credit_after: Decimal = Decimal("0")
    keep: list = field(default_factory=list)
    suspend: list = field(default_factory=list)
    resume: list = field(default_factory=list)
    blocked: str = ""


def preview_change(subscription, plan, keep_ids=None, now=None):
    """
    Moving to a dearer plan costs the price difference for the rest of the paid period (from the balance first,
    nothing below MIN_SURCHARGE). Moving to a cheaper one adds the unused difference to the balance. Either way
    the plan changes now and the billing date stays. Shops beyond the new plan's limits (all shops, and shops on
    a platform it limits, like Magento) are suspended (`keep_ids` chooses which stay; by default the oldest that
    fit); with room to spare, suspended shops that fit come back.
    """
    from shops.models import Shop
    from shops.services import counted_shops, shops_that_fit, suspended_shops

    change = PlanChange(plan=plan)
    blocked = _change_blocked(subscription, plan)
    if blocked:
        change.blocked = blocked
        return change

    now = now or timezone.now()
    current = subscription.plan
    difference = ((plan.price - current.price) * _remaining_share(subscription, now)).quantize(CENT, ROUND_HALF_UP)
    if plan.price > current.price:
        change.direction = "upgrade"
        change.surcharge = difference
        change.credit_used = min(subscription.credit, difference)
        rest = difference - change.credit_used
        change.waived = Decimal("0") < rest < MIN_SURCHARGE
        change.amount_due = Decimal("0") if change.waived else rest
    else:
        change.direction = "downgrade"
        change.credit_added = -difference
    change.credit_after = subscription.credit - change.credit_used + change.credit_added

    counted = list(counted_shops(subscription.user))
    fitting = shops_that_fit(plan, counted)
    if len(fitting) < len(counted):
        if keep_ids is not None:
            keep_ids = set(keep_ids)
            change.keep = [shop for shop in counted if shop.pk in keep_ids]
            too_many = _over_limits(plan, change.keep)
            if too_many:
                change.blocked = too_many
                return change
        else:
            change.keep = fitting
        change.suspend = [shop for shop in counted if shop not in change.keep]
        if any(shop.status in (Shop.Status.PENDING, Shop.Status.PROVISIONING) for shop in change.suspend):
            change.blocked = "Poczekaj, aż zakładany sklep będzie gotowy, albo zostaw go aktywnym."
    else:
        change.keep = counted
        change.resume = shops_that_fit(plan, suspended_shops(subscription.user), kept=counted)
    return change


def change_plan(user, plan, *, keep_ids=None, return_url="", site_url=""):
    """
    Moves to `plan`. Returns (change, payment): a payment when a surcharge has to be paid first (the plan changes
    once it is paid), otherwise None and the change is done.
    """
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().select_related("plan", "user").filter(user=user).first()
        change = preview_change(subscription, plan, keep_ids)
        if change.blocked:
            raise BillingError(change.blocked)
        if change.amount_due:
            if not allowed_return_url(return_url):
                raise BillingError("Nieobsługiwany adres powrotu.")
            payment = Payment.objects.create(
                user=user,
                subscription=subscription,
                plan=plan,
                kind=Payment.Kind.UPGRADE,
                amount=change.amount_due,
                credit_used=change.credit_used,
                currency=plan.currency,
                gateway=get_gateway().name,
                billing_details=_billing_details(user),
            )
            payment.return_url = _with_payment(return_url, payment.pk)
            payment.save(update_fields=["return_url"])
        else:
            payment = None
            old_plan = subscription.plan
            subscription.plan = plan
            subscription.credit = change.credit_after
            subscription.cancel_at_period_end = False
            subscription.save(update_fields=["plan", "credit", "cancel_at_period_end", "updated_at"])
            suspend_ids = [shop.pk for shop in change.suspend]
            transaction.on_commit(
                lambda: _after_plan_change(subscription.pk, old_plan.pk, Decimal("0"), change.credit_added, suspend_ids),
            )
    if payment is None:
        return change, None
    try:
        checkout = get_gateway().start_payment(payment, payer_for(user), return_url=payment.return_url, site_url=site_url)
    except GatewayError:
        logger.exception("Starting upgrade payment %s failed", payment.pk)
        _fail(payment, GATEWAY_UNAVAILABLE)
        raise BillingError(GATEWAY_UNAVAILABLE) from None
    payment.gateway_id = checkout.gateway_id
    payment.gateway_title = checkout.title
    payment.redirect_url = checkout.redirect_url
    payment.save(update_fields=["gateway_id", "gateway_title", "redirect_url"])
    return change, payment


def _after_plan_change(subscription_id, old_plan_id, charged, credit_added, suspend_ids):
    """Shops follow the new plan: those beyond its limit stop, suspended ones come back when there is room."""
    from shops.models import Shop
    from shops.services import counted_shops, resume_up_to_limit, suspend_shops
    from shops.tasks import refresh_shop_resources

    subscription = Subscription.objects.select_related("plan", "user").get(pk=subscription_id)
    plan = subscription.plan
    old_plan = Plan.objects.get(pk=old_plan_id)
    suspended = list(Shop.objects.filter(pk__in=suspend_ids).order_by("created_at", "pk"))
    suspend_shops(suspended)
    resumed = resume_up_to_limit(subscription.user, plan)
    if plan.shop_memory_mb != old_plan.shop_memory_mb:
        resumed_ids = {shop.pk for shop in resumed}
        for shop in counted_shops(subscription.user).filter(status=Shop.Status.ACTIVE):
            if shop.pk not in resumed_ids:
                refresh_shop_resources.delay(shop.pk)
    _send("changed", subscription.pk, {
        "old_plan": old_plan.name,
        "charged": str(charged),
        "credit_added": str(credit_added),
        "suspended": [shop.name for shop in suspended],
        "resumed": [shop.name for shop in resumed],
    })


def _change_blocked(subscription, plan):
    if subscription is None or subscription.status not in (Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE):
        return "Nie masz aktywnego planu. Wybierz plan, żeby go zmieniać."
    if subscription.status == Subscription.Status.PAST_DUE:
        return "Najpierw musi przejść zaległa płatność za obecny plan."
    if plan.pk == subscription.plan_id:
        return "To już Twój plan."
    if not plan.is_active:
        return "Tego planu nie ma już w ofercie."
    if subscription.payments.filter(kind=Payment.Kind.UPGRADE, status=Payment.Status.PENDING).exists():
        return "Poprzednia zmiana planu czeka jeszcze na płatność."
    return ""


def _remaining_share(subscription, now):
    """The part of the paid period still ahead, from 0 to 1."""
    start, end = subscription.current_period_start, subscription.current_period_end
    if not start or not end or end <= now:
        return Decimal("0")
    total = (end - start).total_seconds()
    return min(Decimal(str((end - now).total_seconds() / total)), Decimal("1")) if total > 0 else Decimal("0")


def _over_limits(plan, shops):
    """Why `shops` can't all stay active in `plan`, or "" when they can."""
    from shops.services import PLATFORM_LIMIT_FIELDS, platform_limit

    if len(shops) > plan.max_shops:
        return f"W planie {plan.name} zostawisz najwyżej {plan.max_shops} {_shops(plan.max_shops)}."
    for platform in PLATFORM_LIMIT_FIELDS:
        limit = platform_limit(plan, platform)
        if sum(shop.platform == platform for shop in shops) > limit:
            if limit == 0:
                return f"Plan {plan.name} nie obejmuje sklepów {platform.label}."
            return f"W planie {plan.name} zostawisz najwyżej {limit} {_shops(limit)} {platform.label}."
    return ""


def _shops(count):
    if count == 1:
        return "sklep"
    return "sklepy" if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else "sklepów"
