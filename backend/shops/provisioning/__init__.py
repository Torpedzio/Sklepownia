from django.conf import settings
from django.utils.module_loading import import_string


def get_provisioner():
    return import_string(settings.SHOP_PROVISIONER)()
