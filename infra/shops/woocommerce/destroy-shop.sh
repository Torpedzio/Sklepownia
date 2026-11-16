#!/usr/bin/env bash
# Removes a shop completely: container, files and database.
#   woocommerce/destroy-shop.sh ceramika
set -euo pipefail
cd "$(dirname "$0")/.."
source .env

SLUG="${1:?Podaj slug sklepu}"
DB_NAME="shop_${SLUG//-/_}"

docker rm -f "shop-$SLUG" 2>/dev/null || true
docker volume rm "shop-$SLUG" 2>/dev/null || true
docker compose exec -T -e MYSQL_PWD="$SHOPS_DB_ROOT_PASSWORD" db mariadb -uroot -e \
  "DROP DATABASE IF EXISTS \`$DB_NAME\`; DROP USER IF EXISTS '$DB_NAME'@'%';"
echo "Usunięto sklep $SLUG"
