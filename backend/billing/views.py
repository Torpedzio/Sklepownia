import logging
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsEmailVerified

from . import invoices, services
from .gateways import get_gateway
from .gateways.base import InvalidNotification
from .gateways.fake import FakeGateway
from .models import BillingProfile, Payment, Plan, Subscription
from .serializers import (
    BillingOverviewSerializer,
    BillingProfileSerializer,
    CheckoutResponseSerializer,
    CheckoutSerializer,
    PaymentSerializer,
    PlanChangePreviewSerializer,
    PlanChangeResultSerializer,
    PlanChangeSerializer,
    PlanSerializer,
    SubscriptionSerializer,
)

logger = logging.getLogger(__name__)

VERIFIED = [IsAuthenticated, IsEmailVerified]
PAYMENT_HISTORY_LENGTH = 12


@extend_schema(responses={200: PlanSerializer(many=True)})
@api_view(["GET"])
@permission_classes([AllowAny])
def plans(request):
    """Plans on offer, for the pricing page. Prices are gross."""
    return Response(PlanSerializer(Plan.objects.filter(is_active=True), many=True).data)


@extend_schema(responses={200: BillingOverviewSerializer})
@api_view(["GET"])
@permission_classes(VERIFIED)
def overview(request):
    """The owner's plan, invoice details and recent payments."""
    user = request.user
    # A payment still waiting for its outcome may have been paid meanwhile (e.g. the payer closed the page).
    services.latest_pending(user)
    subscription = Subscription.objects.select_related("plan").filter(user=user).first()
    profile = BillingProfile.objects.filter(user=user).first()
    payments = Payment.objects.filter(user=user).select_related("plan", "invoice")[:PAYMENT_HISTORY_LENGTH]
    return Response({
        "subscription": SubscriptionSerializer(subscription).data if subscription else None,
        "profile": BillingProfileSerializer(profile).data if profile else None,
        "payments": PaymentSerializer(payments, many=True, context={"request": request}).data,
    })


@extend_schema(request=BillingProfileSerializer, responses={200: BillingProfileSerializer})
@api_view(["PUT"])
@permission_classes(VERIFIED)
def profile(request):
    """Saves who pays: a person or a company with NIP, and the address for invoices."""
    instance = BillingProfile.objects.filter(user=request.user).first()
    serializer = BillingProfileSerializer(instance, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(user=request.user)
    return Response(serializer.data)


@extend_schema(
    request=CheckoutSerializer,
    responses={
        201: CheckoutResponseSerializer,
        400: OpenApiResponse(description="Brak danych do faktury, zgód albo plan już aktywny."),
        502: OpenApiResponse(description="Operator płatności nie odpowiada."),
    },
)
@api_view(["POST"])
@permission_classes(VERIFIED)
def checkout(request):
    """Starts the first payment for a plan; the app sends the owner to `redirect_url`."""
    serializer = CheckoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        payment = services.start_checkout(
            request.user,
            data["plan"],
            return_url=data["return_url"],
            site_url=request.build_absolute_uri("/"),
            immediate_start_consent=data["immediate_start_consent"],
        )
    except services.BillingError as error:
        code = status.HTTP_502_BAD_GATEWAY if str(error) == services.GATEWAY_UNAVAILABLE else status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(error)}, status=code)
    return Response(
        {"payment": PaymentSerializer(payment).data, "redirect_url": payment.redirect_url},
        status=status.HTTP_201_CREATED,
    )


@extend_schema(responses={200: PaymentSerializer})
@api_view(["GET"])
@permission_classes(VERIFIED)
def payment_detail(request, payment_id):
    """One payment. While it is pending, the gateway is asked about it too."""
    payment = get_object_or_404(Payment.objects.select_related("plan"), pk=payment_id, user=request.user)
    payment = services.check_with_gateway(payment)
    return Response(PaymentSerializer(payment, context={"request": request}).data)


@extend_schema(request=None, responses={200: SubscriptionSerializer})
@api_view(["POST"])
@permission_classes(VERIFIED)
def cancel(request):
    """Stops renewals; the plan works until the end of the paid period."""
    return _change_subscription(request, services.cancel)


@extend_schema(request=None, responses={200: SubscriptionSerializer})
@api_view(["POST"])
@permission_classes(VERIFIED)
def resume(request):
    """Undoes a cancellation before the period ends."""
    return _change_subscription(request, services.resume)


@extend_schema(request=PlanChangeSerializer, responses={200: PlanChangePreviewSerializer})
@api_view(["POST"])
@permission_classes(VERIFIED)
def change_preview(request):
    """What moving to another plan would cost and which shops it would suspend or bring back. Changes nothing."""
    serializer = PlanChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    subscription = Subscription.objects.select_related("plan", "user").filter(user=request.user).first()
    change = services.preview_change(subscription, data["plan"], data.get("keep_shops"))
    return Response(PlanChangePreviewSerializer(change).data)


@extend_schema(
    request=PlanChangeSerializer,
    responses={
        200: OpenApiResponse(PlanChangeResultSerializer, description="Plan zmieniony."),
        201: OpenApiResponse(PlanChangeResultSerializer, description="Najpierw dopłata: `redirect_url`."),
        400: OpenApiResponse(description="Zmiana niemożliwa: powód w `detail`."),
    },
)
@api_view(["POST"])
@permission_classes(VERIFIED)
def change_plan(request):
    """Moves to another plan now. A dearer one may first need a surcharge, paid like the first payment."""
    serializer = PlanChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        change, payment = services.change_plan(
            request.user, data["plan"], keep_ids=data.get("keep_shops"),
            return_url=data["return_url"], site_url=request.build_absolute_uri("/"),
        )
    except services.BillingError as error:
        code = status.HTTP_502_BAD_GATEWAY if str(error) == services.GATEWAY_UNAVAILABLE else status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(error)}, status=code)
    return Response(
        {
            "change": PlanChangePreviewSerializer(change).data,
            "payment": PaymentSerializer(payment).data if payment else None,
            "redirect_url": payment.redirect_url if payment else None,
        },
        status=status.HTTP_201_CREATED if payment else status.HTTP_200_OK,
    )


def _change_subscription(request, change):
    subscription = Subscription.objects.filter(user=request.user).first()
    if subscription is None:
        return Response({"detail": "Nie masz jeszcze planu."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        change(subscription)
    except services.BillingError as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(SubscriptionSerializer(subscription).data)


@csrf_exempt
def gateway_notification(request):
    """
    Payment notifications from the gateway (Tpay: form post with X-JWS-Signature). Not part of the app's API.
    Answers the acknowledgement the gateway expects, or 400 so it tries again later.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    gateway = get_gateway()
    try:
        result = gateway.parse_notification(request)
    except InvalidNotification as error:
        logger.warning("Rejected payment notification: %s", error)
        return HttpResponse("FALSE", status=400, content_type="text/plain")
    services.apply_result(result)
    return HttpResponse(gateway.notification_ack, content_type="text/plain")


def invoice_pdf(request, token):
    """An invoice's PDF behind a signed link from the app (`invoice.url`). Not part of the app's API."""
    invoice = invoices.from_link(token)
    if invoice is None or not invoice.is_final:
        return HttpResponse("Link do faktury wygasł. Otwórz ją ponownie w aplikacji: Konto → Plan i płatności.",
                            status=404, content_type="text/plain; charset=utf-8")
    return _pdf_response(invoice)


def _pdf_response(invoice):
    response = HttpResponse(bytes(invoice.pdf), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{invoice.filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex"
    return response


def fake_gateway_page(request, payment_id):
    """The simulated gateway's payment page (only with FakeGateway): pay with a test card, or decline."""
    if not isinstance(get_gateway(), FakeGateway):
        raise Http404
    payment = get_object_or_404(Payment.objects.select_related("plan", "user"), pk=payment_id)
    if request.method == "POST" and payment.status == Payment.Status.PENDING:
        paid = request.POST.get("action") == "pay"
        services.apply_result(services.PaymentResult(
            reference=payment.reference,
            paid=paid,
            amount=payment.amount if paid else None,
            card=FakeGateway.saved_card() if paid else None,
            error="" if paid else "Płatność odrzucona na stronie testowej.",
        ))
        return HttpResponseRedirect(payment.return_url)
    return render(request, "billing/fake_gateway.html", {"payment": payment, "platform": settings.PLATFORM_NAME})
