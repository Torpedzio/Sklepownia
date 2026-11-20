<?php
declare(strict_types=1);

namespace Sklepownia\Provisioning\Console\Command;

use Magento\Catalog\Api\CategoryRepositoryInterface;
use Magento\Catalog\Api\ProductRepositoryInterface;
use Magento\Catalog\Model\CategoryFactory;
use Magento\Catalog\Model\Product\Attribute\Source\Status;
use Magento\Catalog\Model\Product\Visibility;
use Magento\Catalog\Model\ProductFactory;
use Magento\Catalog\Model\ResourceModel\Category\CollectionFactory as CategoryCollectionFactory;
use Magento\Catalog\Model\ResourceModel\Product\CollectionFactory as ProductCollectionFactory;
use Magento\CheckoutAgreements\Model\AgreementFactory;
use Magento\Framework\App\Area;
use Magento\Cms\Model\PageFactory;
use Magento\Framework\App\Cache\Manager as CacheManager;
use Magento\Framework\App\Config\ScopeConfigInterface;
use Magento\Framework\App\Config\Storage\WriterInterface;
use Magento\Framework\App\ObjectManager;
use Magento\Framework\App\ResourceConnection;
use Magento\Framework\App\State;
use Magento\Integration\Api\AuthorizationServiceInterface;
use Magento\Integration\Api\IntegrationServiceInterface;
use Magento\Integration\Api\OauthServiceInterface;
use Magento\Integration\Model\Integration;
use Magento\Store\Model\ScopeInterface;
use Magento\Store\Model\Store;
use Magento\Store\Model\StoreManagerInterface;
use Magento\Tax\Api\Data\TaxRuleInterfaceFactory;
use Magento\Tax\Api\TaxRuleRepositoryInterface;
use Magento\Tax\Model\Calculation\RateFactory;
use Magento\Tax\Model\Calculation\RuleFactory;
use Magento\User\Model\UserFactory;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputArgument;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Output\OutputInterface;

/**
 * `bin/magento sklepownia:run <action>`: what the platform does inside a shop, one action per call.
 * Input comes as base64-encoded JSON in the SKLEPOWNIA_DATA environment variable (so passwords never
 * show up in the process list); the result is printed as JSON after OUTPUT_MARKER.
 */
class RunCommand extends Command
{
    private const OUTPUT_MARKER = '@@sklepownia@@';
    // Where the platform keeps what it needs to find again.
    private const SAMPLES_PATH = 'sklepownia/samples/ids';
    private const BANK_PATH = 'sklepownia/bank/';
    // The page Luma's footer links to as the privacy policy; the terms get a link of ours (layout/default.xml).
    private const PRIVACY_PAGE = 'privacy-policy-cookie-restriction-mode';
    private const TERMS_LINK_PATH = 'sklepownia/documents/terms_link';
    private const AGREEMENT_NAME = 'Regulamin sklepu';
    private const TAX_CODE = 'VAT';
    // Classes Magento installs: "Taxable Goods" and "Retail Customer".
    private const PRODUCT_TAX_CLASS = 2;
    private const CUSTOMER_TAX_CLASS = 3;
    private const DEFAULT_STORE = 1;

    /** Settings read back by the `read` action, store-view values first. */
    private const READ_PATHS = [
        'name' => 'general/store_information/name',
        'description' => 'design/head/default_description',
        'email' => 'trans_email/ident_general/email',
        'bank_transfer' => 'payment/banktransfer/active',
        'cash_on_delivery' => 'payment/cashondelivery/active',
        'flatrate' => 'carriers/flatrate/active',
        'flatrate_price' => 'carriers/flatrate/price',
        'freeshipping' => 'carriers/freeshipping/active',
        'freeshipping_subtotal' => 'carriers/freeshipping/free_shipping_subtotal',
        'pickup' => 'carriers/sklepowniapickup/active',
        'prices_include_tax' => 'tax/calculation/price_includes_tax',
        'locale' => 'general/locale/code',
        'currency' => 'currency/options/default',
        'country' => 'general/country/default',
        'timezone' => 'general/locale/timezone',
        'base_url' => 'web/unsecure/base_url',
    ];

    protected function configure(): void
    {
        $this->setName('sklepownia:run')
            ->setDescription('Sklepownia: provisioning and settings of this shop')
            ->addArgument('action', InputArgument::REQUIRED);
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $data = json_decode((string) base64_decode((string) getenv('SKLEPOWNIA_DATA')), true) ?: [];
        try {
            $this->get(State::class)->setAreaCode(Area::AREA_ADMINHTML);
        } catch (\Magento\Framework\Exception\LocalizedException $e) {
            // Already set.
        }
        // Saved values are the defaults for every store view, as when edited in the panel's global scope.
        $this->get(StoreManagerInterface::class)->setCurrentStore(Store::DEFAULT_STORE_ID);
        $action = $input->getArgument('action');
        $result = match ($action) {
            'catalog' => $this->catalog($data),
            'home' => $this->home($data),
            'read' => $this->read(),
            'config' => $this->config($data),
            'taxes' => $this->taxes($data),
            'admin' => $this->admin($data),
            'remove_samples' => $this->removeSamples(),
            'documents' => $this->documents($data),
            'api' => $this->api($data),
            default => throw new \InvalidArgumentException('Unknown action'),
        };
        if ($action !== 'read') {
            // Customers see the change right away.
            $cache = $this->get(CacheManager::class);
            $cache->clean($cache->getAvailableTypes());
        }
        $output->writeln("\n" . self::OUTPUT_MARKER . json_encode($result, JSON_UNESCAPED_UNICODE));
        return Command::SUCCESS;
    }

    /** Categories under the store's root and, in a shop without products, the sample products. */
    private function catalog(array $data): array
    {
        $root = (int) $this->get(StoreManagerInterface::class)->getGroup(1)->getRootCategoryId();
        $ids = [];
        foreach ($data['names'] as $position => $name) {
            $found = $this->get(CategoryCollectionFactory::class)->create()
                ->addAttributeToFilter('name', $name)
                ->addAttributeToFilter('parent_id', $root)
                ->getFirstItem();
            if ($found->getId()) {
                $ids[] = (int) $found->getId();
                continue;
            }
            $category = $this->get(CategoryFactory::class)->create();
            $category->setName($name)
                ->setParentId($root)
                ->setIsActive(true)
                ->setIncludeInMenu(true)
                ->setIsAnchor(true)
                ->setPosition($position + 1)
                ->setStoreId(0);
            $ids[] = (int) $this->get(CategoryRepositoryInterface::class)->save($category)->getId();
        }

        $samples = [];
        $hasProducts = $this->get(ProductCollectionFactory::class)->create()->getSize() > 0;
        if ($data['samples'] && !$hasProducts) {
            $number = 1;
            foreach (array_slice($ids, 0, $data['sample_categories']) as $categoryId) {
                for ($i = 0; $i < $data['per_category']; $i++) {
                    $product = $this->get(ProductFactory::class)->create();
                    $product->setSku('przykladowy-produkt-' . $number)
                        ->setName('Przykładowy produkt ' . $number)
                        ->setUrlKey('przykladowy-produkt-' . $number)
                        ->setAttributeSetId($product->getDefaultAttributeSetId())
                        ->setTypeId('simple')
                        ->setPrice($number * 25 + 24.99)
                        ->setDescription($data['description'])
                        ->setShortDescription($data['description'])
                        ->setVisibility(Visibility::VISIBILITY_BOTH)
                        ->setStatus(Status::STATUS_ENABLED)
                        ->setWebsiteIds([1])
                        ->setTaxClassId(self::PRODUCT_TAX_CLASS)
                        ->setCategoryIds([$categoryId])
                        ->setStockData(['use_config_manage_stock' => 1, 'qty' => 100, 'is_in_stock' => 1]);
                    $samples[] = (int) $this->get(ProductRepositoryInterface::class)->save($product)->getId();
                    $number++;
                }
            }
            $this->write([self::SAMPLES_PATH => json_encode($samples)]);
        }
        return ['categories' => $ids, 'samples' => $samples];
    }

    /** The home page: the shop's name, its description and the newest products instead of the placeholder text. */
    private function home(array $data): array
    {
        $page = $this->get(PageFactory::class)->create()->load('home', 'identifier');
        if (!$page->getId()) {
            return ['page' => null];
        }
        $page->setTitle($data['title'])
            ->setContentHeading($data['title'])
            ->setContent($data['content'])
            ->save();
        return ['page' => (int) $page->getId()];
    }

    /**
     * The terms of sale and privacy policy as the shop's pages, replacing what they said. Customers accept the terms
     * with a checkbox at checkout (a checkout agreement with the same text).
     */
    private function documents(array $data): array
    {
        $pages = [];
        $terms = null;
        foreach ($data['documents'] as $document) {
            $identifier = $document['key'] === 'privacy' ? self::PRIVACY_PAGE : $document['slug'];
            $page = $this->get(PageFactory::class)->create()->load($identifier, 'identifier');
            $page->setIdentifier($identifier)
                ->setTitle($document['title'])
                ->setContentHeading($document['title'])
                ->setContent($document['html'])
                ->setPageLayout('1column')
                ->setIsActive(true)
                ->setStores([Store::DEFAULT_STORE_ID])
                ->save();
            $pages[$document['key']] = $identifier;
            if ($document['key'] === 'terms') {
                $terms = $document;
            }
        }
        if ($terms !== null) {
            $agreement = $this->get(AgreementFactory::class)->create()->load(self::AGREEMENT_NAME, 'name');
            $agreement->setName(self::AGREEMENT_NAME)
                ->setContent($terms['html'])
                ->setCheckboxText($data['checkbox'])
                ->setIsActive(1)
                ->setIsHtml(1)
                // Manual: the customer ticks the box.
                ->setMode(1)
                ->setStores([Store::DEFAULT_STORE_ID])
                ->save();
            $this->write(['checkout/options/enable_agreements' => 1, self::TERMS_LINK_PATH => 1]);
        }
        return ['pages' => $pages];
    }

    private function read(): array
    {
        $config = $this->get(ScopeConfigInterface::class);
        $result = [];
        foreach (self::READ_PATHS as $key => $path) {
            $result[$key] = $config->getValue($path, ScopeInterface::SCOPE_STORE, self::DEFAULT_STORE);
        }
        foreach (['owner', 'number', 'bank'] as $field) {
            $result['bank_' . $field] = $config->getValue(self::BANK_PATH . $field);
        }
        $rule = $this->get(RuleFactory::class)->create()->load(self::TAX_CODE, 'code');
        $rate = $this->get(RateFactory::class)->create()->load(self::TAX_CODE, 'code');
        $result['tax_enabled'] = (bool) $rule->getId();
        $result['tax_rate'] = $rate->getId() ? $rate->getRate() : null;
        return $result;
    }

    /** {path: value} at the default scope; overrides for the store view or website would hide them, so they go. */
    private function config(array $data): array
    {
        $this->write($data);
        return ['saved' => count($data)];
    }

    /** One VAT rate for the shop's country and the rule that applies it to taxable goods, or no rule at all. */
    private function taxes(array $data): array
    {
        $include = $data['include'] ? '1' : '0';
        $display = $data['include'] ? '2' : '1';
        $this->write([
            'tax/defaults/country' => $data['country'],
            'tax/calculation/price_includes_tax' => $include,
            'tax/calculation/shipping_includes_tax' => $include,
            'tax/display/type' => $display,
            'tax/display/shipping' => $display,
            'tax/cart_display/price' => $display,
            'tax/cart_display/subtotal' => $display,
            'tax/cart_display/shipping' => $display,
            'tax/sales_display/price' => $display,
            'tax/sales_display/subtotal' => $display,
            'tax/sales_display/shipping' => $display,
        ]);
        $rate = $this->get(RateFactory::class)->create()->load(self::TAX_CODE, 'code');
        $rate->setCode(self::TAX_CODE)
            ->setTaxCountryId($data['country'])
            ->setTaxRegionId(0)
            ->setTaxPostcode('*')
            ->setRate((float) $data['rate'])
            ->save();
        $rule = $this->get(RuleFactory::class)->create()->load(self::TAX_CODE, 'code');
        $repository = $this->get(TaxRuleRepositoryInterface::class);
        if (!$data['enabled']) {
            if ($rule->getId()) {
                $repository->deleteById((int) $rule->getId());
            }
            return ['rule' => null];
        }
        $taxRule = $rule->getId() ? $repository->get((int) $rule->getId())
            : $this->get(TaxRuleInterfaceFactory::class)->create();
        $taxRule->setCode(self::TAX_CODE)
            ->setTaxRateIds([(int) $rate->getId()])
            ->setCustomerTaxClassIds([self::CUSTOMER_TAX_CLASS])
            ->setProductTaxClassIds([self::PRODUCT_TAX_CLASS])
            ->setPriority(0)
            ->setPosition(0);
        return ['rule' => (int) $repository->save($taxRule)->getId()];
    }

    /** The administrator's e-mail and a new password; whoever was signed in is signed out. */
    private function admin(array $data): array
    {
        $user = $this->get(UserFactory::class)->create()->loadByUsername($data['username']);
        if (!$user->getId()) {
            throw new \RuntimeException('No such administrator');
        }
        $user->setEmail($data['email'])->setPassword($data['password'])->setIsActive(1);
        if (!empty($data['locale'])) {
            // The panel in the shop's language.
            $user->setInterfaceLocale($data['locale']);
        }
        $user->save();
        $connection = $this->get(ResourceConnection::class)->getConnection();
        $connection->delete($connection->getTableName('admin_user_session'), ['user_id = ?' => (int) $user->getId()]);
        $user->getResource()->unlock([(int) $user->getId()]);
        return ['user' => (int) $user->getId()];
    }

    /** A new integration with access to everything, replacing the platform's earlier one; returns its token. */
    private function api(array $data): array
    {
        $integrations = $this->get(IntegrationServiceInterface::class);
        $old = $integrations->findByName($data['name']);
        if ($old->getId()) {
            $integrations->delete($old->getId());
        }
        $integration = $integrations->create([
            'name' => $data['name'],
            'status' => Integration::STATUS_ACTIVE,
            'setup_type' => Integration::TYPE_MANUAL,
        ]);
        $this->get(AuthorizationServiceInterface::class)->grantAllPermissions($integration->getId());
        $oauth = $this->get(OauthServiceInterface::class);
        $oauth->createAccessToken($integration->getConsumerId(), true);
        // Integration tokens work as Bearer tokens only with this on (off by default since 2.4.4).
        $this->write(['oauth/consumer/enable_integration_as_bearer' => '1']);
        // The API's permissions are cached outside the cache types, so cleaning them would keep the old
        // integration's: a new key would be refused until a full flush.
        $cache = $this->get(CacheManager::class);
        $cache->flush($cache->getAvailableTypes());
        return ['token' => $oauth->getAccessToken($integration->getConsumerId())->getToken()];
    }

    private function removeSamples(): array
    {
        $ids = json_decode((string) $this->get(ScopeConfigInterface::class)->getValue(self::SAMPLES_PATH), true) ?: [];
        // Magento deletes products only where it's marked as allowed, as in the panel.
        $this->get(\Magento\Framework\Registry::class)->register('isSecureArea', true, true);
        $repository = $this->get(ProductRepositoryInterface::class);
        $removed = 0;
        foreach ($ids as $id) {
            try {
                $repository->deleteById($repository->getById((int) $id)->getSku());
                $removed++;
            } catch (\Magento\Framework\Exception\NoSuchEntityException $e) {
                // Already removed in the panel.
            }
        }
        $this->write([self::SAMPLES_PATH => '[]']);
        return ['removed' => $removed];
    }

    private function write(array $values): void
    {
        $writer = $this->get(WriterInterface::class);
        foreach ($values as $path => $value) {
            $writer->save($path, $value);
            $writer->delete($path, ScopeInterface::SCOPE_WEBSITES, 1);
            $writer->delete($path, ScopeInterface::SCOPE_STORES, self::DEFAULT_STORE);
        }
        $this->get(\Magento\Framework\App\Config\ReinitableConfigInterface::class)->reinit();
    }

    private function get(string $type)
    {
        return ObjectManager::getInstance()->get($type);
    }
}
