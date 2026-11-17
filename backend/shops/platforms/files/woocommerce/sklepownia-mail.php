<?php
/**
 * Plugin Name: Sklepownia: poczta
 * Description: Wysyła e-maile sklepu przez serwer pocztowy platformy. Nadawcą jest adres sklepu w domenie platformy, a odpowiedzi trafiają na adres kontaktowy sklepu.
 *
 * Installed by the platform (backend/shops/platforms/woocommerce.py), which keeps the relay and the sender
 * address in the `sklepownia_mail` option. Whatever a message was sent from becomes its Reply-To, unless it
 * already has one: WooCommerce sets that itself (the customer for new-order alerts, the shop otherwise).
 */

add_action('phpmailer_init', function ($mailer) {
    $mail = get_option('sklepownia_mail');
    if (!is_array($mail) || empty($mail['host']) || empty($mail['sender'])) {
        return;
    }
    $mailer->isSMTP();
    $mailer->Host = $mail['host'];
    $mailer->Port = (int) $mail['port'];
    $mailer->SMTPAuth = false;
    // The relay is on the shop node's own network.
    $mailer->SMTPAutoTLS = false;

    // WordPress's own messages come from "WordPress <wordpress@shop address>", which nobody reads.
    $from_wordpress = stripos($mailer->From, 'wordpress@') === 0;
    if ($mailer->FromName === 'WordPress') {
        $mailer->FromName = wp_specialchars_decode(get_option('blogname'), ENT_QUOTES);
    }
    if (strcasecmp($mailer->From, $mail['sender']) === 0) {
        return;
    }
    if (!$mailer->getReplyToAddresses()) {
        $mailer->addReplyTo($from_wordpress ? get_option('admin_email') : $mailer->From, $mailer->FromName);
    }
    $mailer->setFrom($mail['sender'], $mailer->FromName, false);
});
