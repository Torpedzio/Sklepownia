from django.conf import settings
from django.utils.module_loading import import_string


def get_gateway():
    return import_string(settings.PAYMENT_GATEWAY)()
