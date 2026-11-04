from django.urls import path

from . import views

urlpatterns = [
    path("", views.page, name="handbook-index"),
    path("<slug:slug>/", views.page, name="handbook-page"),
]
