<?php
/**
 * Sends the shop's e-mail from the platform's address (SKLEPOWNIA_MAIL_FROM). Whatever a message was sent from,
 * by default the shop's contact address (PS_SHOP_EMAIL), becomes its Reply-To, unless it already has one
 * (e.g. the customer, for messages from the contact form).
 *
 * Installed by the platform (backend/shops/platforms/prestashop.py), which also points PrestaShop at the
 * platform's mail relay.
 */
if (!defined('_PS_VERSION_')) {
    exit;
}

class SklepowniaMail extends Module
{
    public function __construct()
    {
        $this->name = 'sklepowniamail';
        $this->tab = 'emailing';
        $this->version = '1.0.0';
        $this->author = 'Sklepownia';
        $this->need_instance = 0;
        $this->ps_versions_compliancy = ['min' => '8.0.0', 'max' => _PS_VERSION_];
        parent::__construct();
        $this->displayName = 'Sklepownia: poczta';
        $this->description = 'Wysyła e-maile sklepu z adresu platformy. Odpowiedzi trafiają na adres kontaktowy sklepu.';
    }

    public function install()
    {
        return parent::install() && $this->registerHook('actionEmailSendBefore');
    }

    /** The parameters are references to Mail::send's own variables, so changing them changes the message. */
    public function hookActionEmailSendBefore($params)
    {
        $sender = Configuration::get('SKLEPOWNIA_MAIL_FROM');
        if (!$sender) {
            return true;
        }
        $from = Validate::isEmail($params['from'])
            ? $params['from']
            : Configuration::get('PS_SHOP_EMAIL', null, null, $params['idShop']);
        if (strcasecmp((string) $from, $sender) === 0) {
            return true;
        }
        if ((empty($params['replyTo']) || !Validate::isEmail($params['replyTo'])) && Validate::isEmail($from)) {
            $params['replyTo'] = $from;
            $params['replyToName'] = $params['fromName'] ?: Configuration::get('PS_SHOP_NAME', null, null, $params['idShop']);
        }
        $params['from'] = $sender;

        return true;
    }
}
