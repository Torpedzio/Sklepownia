from django.urls import path

from . import views

urlpatterns = [
    path("push/devices/", views.register_device, name="push-devices"),
    path("push/devices/forget/", views.forget_device, name="push-forget-device"),
    path("push/preferences/", views.preferences, name="push-preferences"),
]
