from rest_framework import serializers

from .models import ContactMessage


class ContactMessageSerializer(serializers.ModelSerializer):
    message = serializers.CharField(min_length=10, max_length=5000)

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "topic", "message"]
