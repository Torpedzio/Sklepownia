from rest_framework.routers import DefaultRouter

from .views import InvitationViewSet, ShopViewSet

router = DefaultRouter()
router.register('shops', ShopViewSet, basename='shop')
router.register('invitations', InvitationViewSet, basename='invitation')

urlpatterns = router.urls
