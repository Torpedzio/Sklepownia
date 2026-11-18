from django.conf import settings
from django.utils.module_loading import import_string


def get_issuer():
    return import_string(settings.INVOICE_ISSUER)()
