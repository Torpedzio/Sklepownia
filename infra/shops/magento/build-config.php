<?php
// Adds the stores and themes to app/etc/config.php for a build without a database, or removes them again.
// They are what `bin/magento app:config:dump scopes themes` writes on an installed shop.
$file = '/var/www/html/app/etc/config.php';
$config = require $file;
if (($argv[1] ?? '') === 'add') {
    $config['scopes'] = [
        'websites' => [
            'admin' => ['website_id' => '0', 'code' => 'admin', 'name' => 'Admin', 'sort_order' => '0', 'default_group_id' => '0', 'is_default' => '0'],
            'base' => ['website_id' => '1', 'code' => 'base', 'name' => 'Main Website', 'sort_order' => '0', 'default_group_id' => '1', 'is_default' => '1'],
        ],
        'groups' => [
            0 => ['group_id' => '0', 'website_id' => '0', 'name' => 'Default', 'root_category_id' => '0', 'default_store_id' => '0', 'code' => 'default'],
            1 => ['group_id' => '1', 'website_id' => '1', 'name' => 'Main Website Store', 'root_category_id' => '2', 'default_store_id' => '1', 'code' => 'main_website_store'],
        ],
        'stores' => [
            'admin' => ['store_id' => '0', 'code' => 'admin', 'website_id' => '0', 'group_id' => '0', 'name' => 'Admin', 'sort_order' => '0', 'is_active' => '1'],
            'default' => ['store_id' => '1', 'code' => 'default', 'website_id' => '1', 'group_id' => '1', 'name' => 'Default Store View', 'sort_order' => '0', 'is_active' => '1'],
        ],
    ];
    $theme = function ($area, $path, $title, $parent) {
        return ['parent_id' => $parent, 'theme_path' => $path, 'theme_title' => $title, 'is_featured' => '0',
            'area' => $area, 'type' => '0', 'code' => $path];
    };
    $config['themes'] = [
        'adminhtml/Magento/backend' => $theme('adminhtml', 'Magento/backend', 'Magento 2 backend', null),
        // Mage-OS's own admin theme, the panel's default there.
        'adminhtml/MageOS/m137-admin-theme' => $theme('adminhtml', 'MageOS/m137-admin-theme', 'M137 Admin Theme', 'Magento/backend'),
        'frontend/Magento/blank' => $theme('frontend', 'Magento/blank', 'Magento Blank', null),
        'frontend/Magento/luma' => $theme('frontend', 'Magento/luma', 'Magento Luma', 'Magento/blank'),
    ];
} else {
    unset($config['scopes'], $config['themes']);
}
file_put_contents($file, "<?php\nreturn " . var_export($config, true) . ";\n");
