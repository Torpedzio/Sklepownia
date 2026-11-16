# Magento (the Mage-OS distribution, no Adobe keys needed) ready to install: code, compiled
# dependency injection and static files for the shop's themes and languages are all in the image,
# so setting up a shop only installs the database. Each shop keeps its own files in a volume
# at /var/www/data (see entrypoint.sh); the code stays here and is shared by all shops.
FROM php:8.4-apache AS base

ARG MAGEOS_VERSION=4.0.0
ARG LANGUAGE_PL_VERSION=0.0.46

COPY --from=mlocati/php-extension-installer:2.9 /usr/bin/install-php-extensions /usr/local/bin/
RUN install-php-extensions bcmath ftp gd intl opcache pdo_mysql soap sockets xsl zip \
    && apt-get update && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite headers expires deflate \
    && sed -ri 's#/var/www/html#/var/www/html/pub#g' /etc/apache2/sites-available/000-default.conf

FROM base AS build
COPY --from=composer:2.8 /usr/bin/composer /usr/local/bin/composer
WORKDIR /var/www/html
ENV COMPOSER_MEMORY_LIMIT=-1 COMPOSER_ALLOW_SUPERUSER=1
RUN composer create-project --no-dev --no-progress --repository-url=https://repo.mage-os.org/ \
        "mage-os/project-community-edition=${MAGEOS_VERSION}" . \
    && composer require --no-progress --update-no-dev "community-engineering/language-pl_pl:${LANGUAGE_PL_VERSION}" \
    && composer clear-cache

COPY Sklepownia /var/www/html/app/code/Sklepownia
COPY build-config.php /tmp/build-config.php

# Compile and deploy static files without a database: the build needs the stores and themes in
# config.php, which a real installation would put in the database. They are removed afterwards,
# so each shop's installation creates its own and the owner can still edit stores in the panel.
# Two-factor sign-in (the panel's address is random and the password is managed by the platform) and
# the panel's usage tracking and release notes are switched off; Mage-OS lacks some of them, and its
# passkey sign-in builds on two-factor sign-in.
RUN php bin/magento module:enable --all \
    && php bin/magento module:disable $(php bin/magento module:status \
        | grep -oE '^(Magento_(AdminAdobeImsTwoFactorAuth|TwoFactorAuth|AdminAnalytics|ReleaseNotification)|MageOS_PasskeyAuth)$') \
    && php /tmp/build-config.php add \
    && php -d memory_limit=-1 bin/magento setup:di:compile \
    && php -d memory_limit=-1 bin/magento setup:static-content:deploy -f -j 4 \
        --area frontend --theme Magento/luma pl_PL en_US de_DE \
    && php -d memory_limit=-1 bin/magento setup:static-content:deploy -f -j 4 \
        --area adminhtml --theme MageOS/m137-admin-theme --theme Magento/backend pl_PL en_US de_DE \
    && composer dump-autoload --no-dev --optimize \
    && php /tmp/build-config.php remove \
    && rm -rf var/* app/etc/env.php /tmp/build-config.php

FROM base
WORKDIR /var/www/html
# Only for running shops: the build compiles with its own limits.
COPY php.ini /usr/local/etc/php/conf.d/zz-magento.ini
RUN printf '/var/www/data/\n/var/www/html/app/etc/env.php\n' > /usr/local/etc/php/opcache-blacklist.txt
COPY --from=build --chown=www-data:www-data /var/www/html /var/www/html
COPY entrypoint.sh /usr/local/bin/magento-entrypoint
# Per-shop files live in the volume; the code points there.
RUN mv pub/media /opt/media-skeleton \
    && ln -s /var/www/data/media pub/media \
    && rm -rf var && ln -s /var/www/data/var var \
    && ln -s /var/www/data/env.php app/etc/env.php \
    && chown -h www-data:www-data pub/media var app/etc/env.php \
    && chmod +x /usr/local/bin/magento-entrypoint

ENTRYPOINT ["magento-entrypoint"]
CMD ["apache2-foreground"]
