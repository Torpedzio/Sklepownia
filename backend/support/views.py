from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import ContactMessageSerializer
from .tasks import notify_about_contact_message


class ContactView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "contact"

    @extend_schema(request=ContactMessageSerializer, responses={201: ContactMessageSerializer})
    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        with transaction.atomic():
            message = serializer.save(user=user)
            transaction.on_commit(lambda: notify_about_contact_message.delay(message.pk))
        return Response(serializer.data, status=status.HTTP_201_CREATED)
