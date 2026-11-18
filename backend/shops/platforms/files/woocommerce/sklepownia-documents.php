<?php
/**
 * Plugin Name: Sklepownia: regulamin
 * Description: Pokazuje w stopce sklepu odnośniki do regulaminu i polityki prywatności opublikowanych z aplikacji.
 *
 * Installed by the platform (backend/shops/platforms/woocommerce.py), which keeps the pages' IDs in the
 * `sklepownia_documents` option. Themes differ in what their footers show, so the links come after the footer,
 * the same in every theme. A page taken offline in the panel loses its link.
 */

// A theme without a menu lists every page at the top; the documents belong in the footer.
add_filter('wp_page_menu_args', function ($args) {
    $pages = get_option('sklepownia_documents');
    if (is_array($pages) && $pages) {
        $exclude = isset($args['exclude']) ? wp_parse_id_list($args['exclude']) : array();
        $args['exclude'] = implode(',', array_filter(array_merge($exclude, array_map('intval', $pages))));
    }
    return $args;
});

add_action('wp_footer', function () {
    $pages = get_option('sklepownia_documents');
    if (!is_array($pages)) {
        return;
    }
    $links = array();
    foreach (array('terms', 'privacy') as $key) {
        $id = isset($pages[$key]) ? (int) $pages[$key] : 0;
        if ($id && get_post_status($id) === 'publish') {
            $links[] = sprintf('<a href="%s">%s</a>', esc_url(get_permalink($id)), esc_html(get_the_title($id)));
        }
    }
    if (!$links) {
        return;
    }
    printf(
        '<nav class="sklepownia-documents" aria-label="%s" style="clear:both;padding:16px 16px 24px;text-align:center;'
        . 'font-size:14px;line-height:1.6">%s</nav>',
        esc_attr__('Dokumenty sklepu'),
        implode('<span aria-hidden="true" style="margin:0 12px">|</span>', $links)
    );
}, 5);
