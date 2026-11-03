from django.conf import settings
from django.db import models


class ContactMessage(models.Model):
    class Topic(models.TextChoices):
        QUESTION = "question", "Pytanie"
        SHOP_PROBLEM = "shop_problem", "Problem ze sklepem"
        BILLING = "billing", "Płatności i faktury"
        OTHER = "other", "Inne"

    name = models.CharField(max_length=100)
    email = models.EmailField()
    topic = models.CharField(max_length=20, choices=Topic.choices, default=Topic.QUESTION)
    message = models.TextField(max_length=5000)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_handled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_topic_display()}: {self.email}"
