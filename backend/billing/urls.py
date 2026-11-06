from django.urls import path

from . import views

urlpatterns = [
    path("billing/plans/", views.plans, name="billing-plans"),
    path("billing/", views.overview, name="billing-overview"),
    path("billing/profile/", views.profile, name="billing-profile"),
    path("billing/checkout/", views.checkout, name="billing-checkout"),
    path("billing/payments/<int:payment_id>/", views.payment_detail, name="billing-payment"),
    path("billing/subscription/cancel/", views.cancel, name="billing-cancel"),
    path("billing/subscription/resume/", views.resume, name="billing-resume"),
    path("billing/subscription/change-preview/", views.change_preview, name="billing-change-preview"),
    path("billing/subscription/change/", views.change_plan, name="billing-change"),
    path("billing/notifications/", views.gateway_notification, name="billing-notifications"),
    path("billing/fake-gateway/<int:payment_id>/", views.fake_gateway_page, name="billing-fake-gateway"),
]
