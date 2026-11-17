# Sklepy WooCommerce

WordPress 7.1 z WooCommerce w obrazie `shops/wordpress:7.1` z [Dockerfile](Dockerfile): WordPress, WP-CLI,
WooCommerce i motywy (Storefront, Astra, Kadence). Pliki sklepu (WordPress z wtyczkami i zdjęciami) są
w wolumenie `shop-<id>` na `/var/www/html`. Backend: [woocommerce.py](../../../backend/shops/platforms/woocommerce.py),
wszystko w sklepie robi przez WP-CLI.

## Kroki i czasy

Czasy są orientacyjne, zmierzone na zwykłym laptopie.

| Krok | Co robi | Czas |
|---|---|---|
| Baza produktów i zamówień | `CREATE DATABASE/USER` w MariaDB, osobne hasło na sklep | ~0 s |
| Uruchomienie sklepu | `docker run` z etykietami Traefika i limitami pamięci z planu / 1 CPU; czekanie na `wp-config.php` | ~5 s |
| Strona i konto administratora | `wp core install`, usunięcie domyślnych wpisów i stron | ~4 s |
| Język i strefa czasowa | pakiet językowy, strefa czasowa z kraju, permalinki `/%postname%/` | ~8 s |
| Waluta, koszyk i zamówienia | tłumaczenie → aktywacja → waluta, format cen, jednostki, e-mail; wyłączenie trybu „coming soon” i kreatora; strony sklepu; sklep jako strona główna | ~30 s |
| Wygląd sklepu | aktywacja motywu z obrazu, usunięcie domyślnych widgetów, tłumaczenie | ~5 s |
| Kategorie produktów | kategorie (pierwsza zastępuje domyślne „Bez kategorii”) i opcjonalnie 6 przykładowych produktów | ~25 s |
| Wyszukiwarka i filtry | lewy pasek boczny sklepu: wyszukiwarka, menu kategorii, aktywne filtry, filtr ceny i ocen; ustawienia zależne od motywu | ~15 s |
| Połączenie z aplikacją | Application Password `platform` dla admina | ~3 s |
| Końcowe sprawdzenie | strona główna 200 i `wc/v3/system_status` z hasłem API | ~4 s |
| **Razem** | | **~105 s** |

## Zakładanie i usuwanie sklepu ręcznie

Skrypt robi to samo co backend i przydaje się do eksperymentów. Uruchamia się z `infra/shops`:

```bash
woocommerce/provision-shop.sh --slug ceramika --name "Pracownia Ceramiki" --email ja@example.com \
    --theme storefront --categories "Kubki,Talerze,Wazony" --sample-products
woocommerce/destroy-shop.sh ceramika
```

Opcje: `--theme storefront|astra|kadence`, `--language pl_PL|en_US|de_DE`,
`--currency PLN|EUR|USD|GBP`, `--country PL|DE|CZ|SK|GB|US`.
Skrypt na końcu wypisuje adres, login i hasło do wp-admin oraz hasło API.
Sklepy ze skryptu nie są widoczne w aplikacji.

## Uwagi techniczne

- **Widgety:** domyślny motyw WordPressa jest blokowy i nie ma pasków bocznych, więc `widget reset`
  działa dopiero po aktywacji motywu z paskiem bocznym (Storefront).
- **Kolejność ma znaczenie:** tłumaczenie WooCommerce trzeba zainstalować **przed** aktywacją wtyczki,
  bo aktywacja tworzy strony sklepu w aktywnym języku. W odwrotnej kolejności powstają „Cart” i „Checkout”.
- **WooCommerce 11:** opcja `woocommerce_task_list_hidden` jest martwa (`wp option update` zwraca błąd).
  Zastępuje ją `woocommerce_task_list_hidden_lists`. Nowe sklepy startują w trybie „coming soon”,
  który trzeba wyłączyć (`woocommerce_coming_soon=no`).
- **Klucze API:** zamiast kluczy WooCommerce (`ck_`/`cs_`, których nie da się wygenerować z WP-CLI)
  używamy Application Password. WooCommerce REST API przyjmuje go przez Basic Auth.
  Przez HTTP działa tylko przy `WP_ENVIRONMENT_TYPE=local` (`SHOPS_WP_ENVIRONMENT`); na produkcji potrzebny jest HTTPS.
- **Poczta:** WordPress bez konfiguracji wysyła przez `mail()`, którego w kontenerze nie ma. Wtyczka „must-use”
  `wp-content/mu-plugins/sklepownia-mail.php` kieruje pocztę do przekaźnika ([poczta sklepów](../README.md#poczta-sklepów)).
  Wtyczki „must-use” nie da się wyłączyć w panelu. Skrypt `provision-shop.sh` poczty nie ustawia.
- **Czas:** najwięcej kosztuje start WP-CLI przy każdym poleceniu (~1–2 s). Zgrupowanie konfiguracji
  WooCommerce i kategorii w jednym `wp eval-file` powinno skrócić całość do ~30 s.
  Pakiety językowe też można wbudować w obraz.
