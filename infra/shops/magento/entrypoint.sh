#!/bin/sh
# The shop's own files live in the volume at /var/www/data: settings (env.php), product images and var/.
set -e
DATA=/var/www/data
mkdir -p "$DATA/var"
if [ ! -d "$DATA/media" ]; then
    cp -a /opt/media-skeleton "$DATA/media"
fi
chown www-data:www-data "$DATA" "$DATA/var" "$DATA/media"

# Magento's scheduled jobs (indexes, e-mails, prices), once a minute, once the installation has finished
# (it writes the installation date last). Errors go to Magento's own logs in var/log.
(
    while true; do
        sleep 60
        if [ -s "$DATA/env.php" ] && grep -q "'date'" "$DATA/env.php"; then
            su www-data -s /bin/sh -c "php /var/www/html/bin/magento cron:run" > /dev/null 2>&1 || true
        fi
    done
) &

exec docker-php-entrypoint "$@"
