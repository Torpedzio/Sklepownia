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
        """Saves through the webservice, which takes XML: <prestashop><resource><field>…; answers in JSON."""
        root = ElementTree.Element("prestashop")
        node = ElementTree.SubElement(root, resource)
        for name, value in fields.items():
            ElementTree.SubElement(node, name).text = "" if value is None else str(value)
        body = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
        return self.request(method, path, params=params, data=body, headers={"Content-Type": "application/xml"})
