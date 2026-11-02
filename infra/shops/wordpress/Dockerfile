# WordPress with WP-CLI, WooCommerce and shop themes baked in, so provisioning
# a shop doesn't download them every time.
FROM wordpress:7.1.4-php8.3-apache

ARG WP_CLI_VERSION=2.12.0
ARG WOOCOMMERCE_VERSION=11.2.1
ARG STOREFRONT_VERSION=4.6.2
ARG ASTRA_VERSION=4.14.2
ARG KADENCE_VERSION=1.5.2

RUN apt-get update \
    && apt-get install -y --no-install-recommends less unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /usr/local/bin/wp \
        "https://github.com/wp-cli/wp-cli/releases/download/v${WP_CLI_VERSION}/wp-cli-${WP_CLI_VERSION}.phar" \
    && chmod +x /usr/local/bin/wp

# The entrypoint copies /usr/src/wordpress into the volume on first start.
RUN set -eux; cd /tmp; \
    curl -fsSL -o p.zip "https://downloads.wordpress.org/plugin/woocommerce.${WOOCOMMERCE_VERSION}.zip"; \
    unzip -q p.zip -d /usr/src/wordpress/wp-content/plugins; \
    for theme in "storefront ${STOREFRONT_VERSION}" "astra ${ASTRA_VERSION}" "kadence ${KADENCE_VERSION}"; do \
        set -- $theme; \
        curl -fsSL -o t.zip "https://downloads.wordpress.org/theme/$1.$2.zip"; \
        unzip -q t.zip -d /usr/src/wordpress/wp-content/themes; \
    done; \
    rm -rf /usr/src/wordpress/wp-content/plugins/akismet /usr/src/wordpress/wp-content/plugins/hello.php p.zip t.zip; \
    chown -R www-data:www-data /usr/src/wordpress/wp-content

ENV WP_CLI_CACHE_DIR=/tmp/wp-cli-cache
