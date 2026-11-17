class ProvisioningError(Exception):
    pass


class BaseProvisioner:
    """
    Sets up a shop on one platform step by step: the steps are listed in shops/platforms/__init__.py.

    Every step must be idempotent: a retry creates a new job and runs all steps
    again, so a step has to cope with work left behind by a failed attempt.
    Implementations define a `step_<key>(shop)` method for each step.
    """

    def run_step(self, key, shop):
        getattr(self, f"step_{key}")(shop)

    def cleanup(self, shop):
        """Called after a failed run. Must be safe to call anytime."""

    def teardown(self, shop):
        """Remove everything the shop uses. Must be safe to call more than once."""

    def update_address(self, shop):
        """
        Move a running shop to its current `shop.url`, e.g. after SHOPS_BASE_DOMAIN changed.
        Returns the previous address, or None when there is nothing to move.
        """
        return None

    def suspend(self, shop):
        """Stop serving the shop, keeping everything it has. Safe to call more than once."""

    def resume(self, shop):
        """Serve a suspended shop again, with the resources its owner's plan gives now."""

    def refresh_resources(self, shop):
        """Apply the owner's current plan (e.g. memory) to a running shop."""

    def configure_mail(self, shop):
        """
        Send the running shop's e-mail through the platform's mail relay (settings SHOPS_SMTP_*), from the shop's
        own sender address. Returns False when the shop has nothing running to configure.
        """
        return False

    # --- running shops (see provisioning/operations.py) ---

    def read_settings(self, shop):
        """The shop's current settings, {section: {field: value}} as in shops/shop_settings.py."""
        raise NotImplementedError

    def apply_settings(self, shop, changes, values):
        """
        Make the shop match `changes` ({section: {field: new value}}, only what changed).
        `values` are the complete settings after the change, for sections that need them all.
        `shop` and `shop.config` already carry the new name, language, currency, country and theme.
        """
        raise NotImplementedError

    def reset_admin_password(self, shop):
        """Give the shop administrator a new password and store it in the shop's credentials."""
        raise NotImplementedError

    def remove_sample_products(self, shop):
        """Delete the sample products added at provisioning. Returns how many were removed."""
        raise NotImplementedError
