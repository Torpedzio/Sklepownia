<?php
declare(strict_types=1);

namespace Sklepownia\Provisioning\Plugin;

use Magento\Framework\App\Config\ScopeConfigInterface;
use Magento\Framework\Mail\TransportInterface;
use Symfony\Component\Mime\Address;

/**
 * Every e-mail goes out from the platform's address (sklepownia/mail/sender), which the mail provider can sign.
 * Whatever it was sent from, one of the shop's own addresses, becomes its Reply-To unless it has one already
 * (the contact form sets the customer). The platform sets the address (backend/shops/platforms/magento.py).
 */
class MailSender
{
    public const SENDER_PATH = 'sklepownia/mail/sender';

    public function __construct(private readonly ScopeConfigInterface $config)
    {
    }

    public function beforeSendMessage(TransportInterface $transport): void
    {
        $sender = (string) $this->config->getValue(self::SENDER_PATH);
        $message = $transport->getMessage();
        if ($sender === '' || !method_exists($message, 'getSymfonyMessage')) {
            return;
        }
        $headers = $message->getSymfonyMessage()->getHeaders();
        $fromHeader = $headers->get('From');
        $from = $fromHeader ? $fromHeader->getAddresses() : [];
        if (count($from) === 1 && strcasecmp($from[0]->getAddress(), $sender) === 0) {
            return;
        }
        if ($from && !$headers->has('Reply-To')) {
            $headers->addMailboxListHeader('Reply-To', $from);
        }
        $address = new Address($sender, $from ? $from[0]->getName() : '');
        if ($fromHeader) {
            $fromHeader->setAddresses([$address]);
        } else {
            $headers->addMailboxListHeader('From', [$address]);
        }
    }
}
