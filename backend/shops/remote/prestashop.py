from xml.etree import ElementTree

from . import ShopApi


class PrestaShopApi(ShopApi):
    """PrestaShop's webservice: JSON answers, but data to save goes as XML."""

    def authenticate(self, session, credentials):
        session.auth = (credentials.api_key, "")

    def address(self, path, params):
        # The dispatcher works without friendly URLs, which /api/ needs.
        return f"{self.shop.url}/webservice/dispatcher.php", {**params, "url": path.strip("/"), "output_format": "JSON"}

    def error_message(self, body):
        return "; ".join(error["message"] for error in body["errors"])

    def ping(self):
        # Not the list of resources: PrestaShop 9.2 fails to give it as JSON.
        self.get("shops")

    def send_xml(self, method, path, resource, fields, params=None):
        """
        Saves through the webservice, which takes XML: <prestashop><resource><field>…; answers in JSON. A value is
        text, Translated ({language id: text}) for a field per language, or a list of (tag, value) for nested ones,
        e.g. the product's associations.
        """
        root = ElementTree.Element("prestashop")
        _fill(ElementTree.SubElement(root, resource), fields.items())
        body = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
        return self.request(method, path, params=params, data=body, headers={"Content-Type": "application/xml"})


class Translated(dict):
    """{language id: text} of a field kept per language."""


def _fill(node, items):
    for name, value in items:
        child = ElementTree.SubElement(node, name)
        if isinstance(value, Translated):
            for language, text in value.items():
                ElementTree.SubElement(child, "language", id=str(language)).text = text
        elif isinstance(value, dict):
            _fill(child, value.items())
        elif isinstance(value, list):
            _fill(child, value)
        else:
            child.text = "" if value is None else str(value)
