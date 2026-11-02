#!/usr/bin/env bash
# Sets up a WordPress + WooCommerce shop in its own container.
# Every step is idempotent: running the script again for the same slug
# finishes a half-done shop instead of breaking it.
#
#   ./provision-shop.sh --slug ceramika --name "Pracownia Ceramiki" --email ja@example.com \
#       [--theme storefront] [--language pl_PL] [--currency PLN] [--country PL] \
#       [--categories "Kubki,Talerze,Wazony"] [--sample-products]
set -eEuo pipefail
cd "$(dirname "$0")"
source .env

SLUG="" NAME="" EMAIL="" THEME="storefront" LANGUAGE="pl_PL" CURRENCY="PLN" COUNTRY="PL"
CATEGORIES="" SAMPLE_PRODUCTS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --slug) SLUG="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --theme) THEME="$2"; shift 2 ;;
    --language) LANGUAGE="$2"; shift 2 ;;
    --currency) CURRENCY="$2"; shift 2 ;;
    --country) COUNTRY="$2"; shift 2 ;;
    --categories) CATEGORIES="$2"; shift 2 ;;
    --sample-products) SAMPLE_PRODUCTS=1; shift ;;
    *) echo "Nieznany argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$SLUG" =~ ^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$ ]] || { echo "Nieprawidłowy --slug" >&2; exit 2; }
[[ -n "$NAME" && -n "$EMAIL" ]] || { echo "Wymagane: --name i --email" >&2; exit 2; }

CONTAINER="shop-$SLUG"
VOLUME="shop-$SLUG"
DB_NAME="shop_${SLUG//-/_}"
HOST="$SLUG.$SHOPS_DOMAIN"
URL="http://$HOST:$SHOPS_HTTP_PORT"
ADMIN_USER="admin"
ADMIN_PASSWORD="(bez zmian)"
APP_PASSWORD=""

wpc() { docker exec -u www-data "$CONTAINER" wp --path=/var/www/html "$@"; }
sql() { docker compose exec -T -e MYSQL_PWD="$SHOPS_DB_ROOT_PASSWORD" db mariadb -uroot -e "$1"; }
random() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }

LOG=$(mktemp)
exec 3>&1
# Not `step ... || handle`: bash disables errexit inside functions called that way.
# Writes to fd 3 because inside a step stdout points at the log.
trap 'echo "BŁĄD" >&3; cat "$LOG" >&3; exit 1' ERR

step() {
  local label="$1"; shift
  local start=$SECONDS
  printf '▸ %-34s' "$label"
  "$@" > "$LOG" 2>&1
  echo "ok ($((SECONDS - start)) s)"
}

create_database() {
  # Reuse the password of an existing container so a re-run doesn't lock it out.
  DB_PASSWORD=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER" 2>/dev/null \
    | sed -n 's/^WORDPRESS_DB_PASSWORD=//p' || true)
  DB_PASSWORD=${DB_PASSWORD:-$(random 24)}
  sql "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
       CREATE USER IF NOT EXISTS '$DB_NAME'@'%' IDENTIFIED BY '$DB_PASSWORD';
       ALTER USER '$DB_NAME'@'%' IDENTIFIED BY '$DB_PASSWORD';
       GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_NAME'@'%';"
}

start_container() {
  if ! docker container inspect "$CONTAINER" > /dev/null 2>&1; then
    docker run -d --name "$CONTAINER" --restart unless-stopped \
      --network shops --memory 512m --cpus 1 \
      -v "$VOLUME:/var/www/html" \
      -e WORDPRESS_DB_HOST=shops-db \
      -e WORDPRESS_DB_NAME="$DB_NAME" \
      -e WORDPRESS_DB_USER="$DB_NAME" \
      -e WORDPRESS_DB_PASSWORD="$DB_PASSWORD" \
      -e WORDPRESS_CONFIG_EXTRA="define('WP_ENVIRONMENT_TYPE', 'local'); define('DISALLOW_FILE_EDIT', true);" \
      -l traefik.enable=true \
      -l "traefik.http.routers.$CONTAINER.rule=Host(\`$HOST\`)" \
      -l "traefik.http.routers.$CONTAINER.entrypoints=web" \
      -l "traefik.http.services.$CONTAINER.loadbalancer.server.port=80" \
      -l "shops.slug=$SLUG" \
      shops/wordpress:7.1
  fi
  docker start "$CONTAINER"
  # The entrypoint copies WordPress into the volume and writes wp-config.php.
  for _ in $(seq 60); do
    docker exec "$CONTAINER" test -f /var/www/html/wp-config.php && return 0
    sleep 1
  done
  return 1
}

install_wordpress() {
  if ! wpc core is-installed; then
    ADMIN_PASSWORD=$(random 18)
    wpc core install --url="$URL" --title="$NAME" --admin_user="$ADMIN_USER" \
      --admin_password="$ADMIN_PASSWORD" --admin_email="$EMAIL" --skip-email
    # Drop "Hello world", "Sample Page" etc. Only right after install, never on re-runs.
    wpc post delete $(wpc post list --post_type=post,page --post_status=any --format=ids) --force
    wpc widget reset --all
  fi
  wpc option update blogname "$NAME"
  wpc option update blogdescription ""
}

configure_locale() {
  if [[ "$LANGUAGE" != "en_US" ]]; then
    wpc language core install "$LANGUAGE"
    wpc site switch-language "$LANGUAGE"
  fi
  local timezone
  case "$COUNTRY" in
    PL) timezone=Europe/Warsaw ;; DE) timezone=Europe/Berlin ;; CZ) timezone=Europe/Prague ;;
    SK) timezone=Europe/Bratislava ;; GB) timezone=Europe/London ;; US) timezone=America/New_York ;;
    *) timezone=UTC ;;
  esac
  wpc option update timezone_string "$timezone"
  wpc rewrite structure '/%postname%/'
  wpc rewrite flush --hard
}

configure_woocommerce() {
  # Translation first: activation creates the shop pages using the active language.
  [[ "$LANGUAGE" == "en_US" ]] || wpc language plugin install woocommerce "$LANGUAGE"
  wpc plugin is-active woocommerce || wpc plugin activate woocommerce

  local position="left" thousand="," decimal="."
  case "$CURRENCY" in
    PLN|EUR) position="right_space" thousand=" " decimal="," ;;
  esac
  wpc option update woocommerce_default_country "$COUNTRY"
  wpc option update woocommerce_currency "$CURRENCY"
  wpc option update woocommerce_currency_pos "$position"
  wpc option update woocommerce_price_thousand_sep "$thousand"
  wpc option update woocommerce_price_decimal_sep "$decimal"
  wpc option update woocommerce_weight_unit kg
  wpc option update woocommerce_dimension_unit cm
  wpc option update woocommerce_email_from_address "$EMAIL"
  wpc option update woocommerce_email_from_name "$NAME"
  # New stores start in "coming soon" mode and with the onboarding wizard; skip both.
  wpc option update woocommerce_coming_soon no
  wpc option update woocommerce_onboarding_profile '{"skipped":true}' --format=json
  wpc option update woocommerce_task_list_hidden_lists '["setup","extended"]' --format=json
  wpc option update woocommerce_allow_tracking no
  wpc option update woocommerce_show_marketplace_suggestions no
  wpc wc tool run install_pages --user="$ADMIN_USER"
  wpc option update show_on_front page
  wpc option update page_on_front "$(wpc option get woocommerce_shop_page_id)"
}

install_theme() {
  wpc theme activate "$THEME"
  [[ "$LANGUAGE" == "en_US" ]] || wpc language theme install "$THEME" "$LANGUAGE" || true
}

create_categories() {
  [[ -n "$CATEGORIES" ]] || return 0
  local ids=() name id
  IFS=',' read -ra names <<< "$CATEGORIES"
  for name in "${names[@]}"; do
    id=$(wpc term list product_cat --name="$name" --field=term_id)
    [[ -n "$id" ]] || id=$(wpc wc product_cat create --name="$name" --user="$ADMIN_USER" --porcelain)
    ids+=("$id")
  done

  if [[ $SAMPLE_PRODUCTS == 1 && $(wpc wc product list --user="$ADMIN_USER" --format=count) == 0 ]]; then
    local i=1
    for id in "${ids[@]:0:3}"; do
      for _ in 1 2; do
        wpc wc product create --user="$ADMIN_USER" --porcelain --name="Przykładowy produkt $i" \
          --type=simple --status=publish --regular_price="$((i * 25 + 24)).99" \
          --description="To jest przykładowy produkt. Zmień jego opis, zdjęcia i cenę w panelu sklepu." \
          --categories="[{\"id\":$id}]"
        i=$((i + 1))
      done
    done
  fi
}

generate_api_keys() {
  # The platform talks to the shop's WP/WooCommerce REST API with an application password.
  local uuid
  for uuid in $(wpc user application-password list "$ADMIN_USER" --name=platform --field=uuid); do
    wpc user application-password delete "$ADMIN_USER" "$uuid"
  done
  APP_PASSWORD=$(wpc user application-password create "$ADMIN_USER" platform --porcelain)
}

health_check() {
  curl -fsS -o /dev/null "$URL/"
  curl -fsS -o /dev/null -u "$ADMIN_USER:$APP_PASSWORD" "$URL/wp-json/wc/v3/system_status"
}

TOTAL_START=$SECONDS
echo "Zakładanie sklepu $NAME → $URL"
step "Tworzenie bazy danych" create_database
step "Uruchamianie WordPressa" start_container
step "Instalacja WordPressa" install_wordpress
step "Ustawienia języka i regionu" configure_locale
step "Konfiguracja WooCommerce" configure_woocommerce
step "Instalacja motywu" install_theme
step "Tworzenie kategorii" create_categories
step "Generowanie kluczy API" generate_api_keys
step "Sprawdzanie działania sklepu" health_check

cat <<OUT

Gotowe w $((SECONDS - TOTAL_START)) s.
  Sklep:      $URL
  Panel:      $URL/wp-admin
  Login:      $ADMIN_USER
  Hasło:      $ADMIN_PASSWORD
  Hasło API:  $APP_PASSWORD
OUT
