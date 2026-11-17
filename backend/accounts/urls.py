from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('logout-everywhere/', views.LogoutEverywhereView.as_view(), name='logout-everywhere'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('delete-account/', views.DeleteAccountView.as_view(), name='delete-account'),
    path('password-reset/', views.PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/confirm/', views.PasswordResetView.as_view(), name='password-reset-confirm'),
    path('me/', views.MeView.as_view(), name='me'),
    path('avatar/', views.AvatarView.as_view(), name='avatar'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('resend-verification/', views.ResendVerificationView.as_view(), name='resend-verification'),
]
