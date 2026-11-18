from django.conf import settings
from django.utils.module_loading import import_string


def get_sender():
    return import_string(settings.PUSH_SENDER)()
