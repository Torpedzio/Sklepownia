# Serwer sklepów

Tu działają sklepy WordPress + WooCommerce i PrestaShop, każdy we własnym kontenerze.
Sklepy zakłada backend: worker Celery wykonuje kroki z
[docker_provisioner.py](../../backend/shops/provisioning/docker_provisioner.py) (WooCommerce) albo
[prestashop.py](../../backend/shops/provisioning/prestashop.py) przez socket Dockera.
Skrypt `provision-shop.sh` robi to samo ręcznie i przydaje się do eksperymentów.

Sklepy z backendu mają kontener i wolumen `shop-<id>` oraz bazę `shop_<id>`.
Sklepy ze skryptu nazywają się według sluga (`shop-<slug>`), więc obie pule się nie mieszają.
Całość systemu: [docs/architektura.md](../../docs/architektura.md).

```
przeglądarka ──▶ Traefik :8080 ──Host: <slug>.<SHOPS_BASE_DOMAIN>──▶ kontener shop-<id> (WordPress + WooCommerce)
                                                                         │
                                                 MariaDB (shops-db), osobna baza i użytkownik na sklep
```

## Uruchomienie

```bash
cd infra/shops
cp .env.example .env               # wpisz SHOPS_DB_ROOT_PASSWORD
docker compose build wordpress     # obraz sklepu: WP 7.1 + WP-CLI + WooCommerce + motywy
docker compose up -d               # Traefik + MariaDB
```

Sklepy są na porcie **8080**, żeby nie kolidować z innymi serwerami na 80/443.
Przeglądarki i curl same rozwiązują `*.localhost` na 127.0.0.1, więc nie trzeba konfigurować DNS.

## Sklepy na telefonie

Na telefonie `localhost` to sam telefon, więc sklepy potrzebują domeny wskazującej na komputer.
Wystarczy publiczny DNS sslip.io: `<slug>.192-168-1-20.sslip.io` rozwiązuje się na `192.168.1.20`.

```bash
# w głównym .env
SHOPS_BASE_DOMAIN=192-168-1-20.sslip.io
docker compose up -d backend worker
docker compose exec worker python manage.py update_shop_addresses
```

Polecenie odtwarza kontener każdego działającego sklepu z nową regułą Traefika (pliki zostają w wolumenie)
i podmienia adres w bazie WordPressa (`wp search-replace`). Trzeba je powtórzyć, gdy komputer dostanie
inny adres IP, np. w innej sieci Wi-Fi. Niektóre routery blokują domeny wskazujące na adresy prywatne
(ochrona przed DNS rebinding); wtedy sslip.io nie zadziała w tej sieci.
Sklepy ze skryptu `provision-shop.sh` mają adres ustalony przy zakładaniu i polecenie ich nie obejmuje.

## Zakładanie i usuwanie sklepu

```bash
./provision-shop.sh --slug ceramika --name "Pracownia Ceramiki" --email ja@example.com \
    --theme storefront --categories "Kubki,Talerze,Wazony" --sample-products
./destroy-shop.sh ceramika
```

Opcje: `--theme storefront|astra|kadence`, `--language pl_PL|en_US|de_DE`,
`--currency PLN|EUR|USD|GBP`, `--country PL|DE|CZ|SK|GB|US`.
Skrypt na końcu wypisuje adres, login i hasło do wp-admin oraz hasło API.

## Kroki i czasy

Kroki odpowiadają `BaseProvisioner.STEPS` w backendzie. Czasy są orientacyjne, zmierzone na zwykłym laptopie.

| Krok | Co robi | Czas |
|---|---|---|
| Baza produktów i zamówień | `CREATE DATABASE/USER` w MariaDB, osobne hasło na sklep | ~0 s |
| Uruchomienie sklepu | `docker run` z etykietami Traefika i limitami 512 MB / 1 CPU; czekanie na `wp-config.php` | ~5 s |
| Strona i konto administratora | `wp core install`, usunięcie domyślnych wpisów i stron | ~4 s |
| Język i strefa czasowa | pakiet językowy, strefa czasowa z kraju, permalinki `/%postname%/` | ~8 s |
| Waluta, koszyk i zamówienia | tłumaczenie → aktywacja → waluta, format cen, jednostki, e-mail; wyłączenie trybu „coming soon” i kreatora; strony sklepu; sklep jako strona główna | ~30 s |
| Wygląd sklepu | aktywacja motywu z obrazu, usunięcie domyślnych widgetów, tłumaczenie | ~5 s |
| Kategorie produktów | kategorie (pierwsza zastępuje domyślne „Bez kategorii”) i opcjonalnie 6 przykładowych produktów | ~25 s |
| Wyszukiwarka i filtry | lewy pasek boczny sklepu: wyszukiwarka, menu kategorii, aktywne filtry, filtr ceny i ocen; ustawienia zależne od motywu | ~15 s |
| Połączenie z aplikacją | Application Password `platform` dla admina | ~3 s |
| Końcowe sprawdzenie | strona główna 200 i `wc/v3/system_status` z hasłem API | ~4 s |
| **Razem** | | **~105 s** |

## Uwagi techniczne

- **Każdy krok jest idempotentny.** Ponowne uruchomienie dokańcza sklep (w aplikacji: „Spróbuj ponownie”).
  Backend zapisuje hasła (bazy, admina, API) w `ShopCredentials` **zanim** ich użyje.
- **Widgety:** domyślny motyw WordPressa jest blokowy i nie ma pasków bocznych, więc `widget reset`
  działa dopiero po aktywacji motywu z paskiem bocznym (Storefront).
- **Kolejność ma znaczenie:** tłumaczenie WooCommerce trzeba zainstalować **przed** aktywacją wtyczki,
  bo aktywacja tworzy strony sklepu w aktywnym języku. W odwrotnej kolejności powstają „Cart” i „Checkout”.
- **WooCommerce 11:** opcja `woocommerce_task_list_hidden` jest martwa (`wp option update` zwraca błąd).
  Zastępuje ją `woocommerce_task_list_hidden_lists`. Nowe sklepy startują w trybie „coming soon”,
  który trzeba wyłączyć (`woocommerce_coming_soon=no`).
- **Klucze API:** zamiast kluczy WooCommerce (`ck_`/`cs_`, których nie da się wygenerować z WP-CLI)
  używamy Application Password. WooCommerce REST API przyjmuje go przez Basic Auth.
  Przez HTTP działa tylko przy `WP_ENVIRONMENT_TYPE=local`; na produkcji potrzebny jest HTTPS.
- **Czas:** najwięcej kosztuje start WP-CLI przy każdym poleceniu (~1–2 s). Zgrupowanie konfiguracji
  WooCommerce i kategorii w jednym `wp eval-file` powinno skrócić całość do ~30 s.
  Pakiety językowe też można wbudować w obraz.
- **Nazwy kategorii:** backend dobiera je do branży i liczby kategorii
  ([categories.py](../../backend/shops/categories.py)). Skrypt przyjmuje gotową listę.
- **Dostęp do Dockera:** Traefik i worker backendu używają `docker.sock` (na systemach z SELinux z `label=disable`).
  Dla workera to w praktyce uprawnienia roota; przed produkcją trzeba go odseparować
  ([docs/ograniczenia-i-plan.md](../../docs/ograniczenia-i-plan.md)).

## PrestaShop

Sklepy PrestaShop działają na oficjalnym obrazie `prestashop/prestashop:9.2.1-apache` (`SHOPS_PRESTASHOP_IMAGE`),
bez własnego Dockerfile. Pierwsze zakładanie pobiera obraz (~1 GB), jeśli go nie ma: `docker pull prestashop/prestashop:9.2.1-apache`.

| Krok | Co robi | Czas |
|---|---|---|
| Uruchomienie sklepu | kontener z `PS_INSTALL_AUTO=0`, wolumen na `/var/www/html`; gotowy, gdy Apache odpowiada | ~5 s |
| Sklep, język i konto administratora | `install/index_cli.php` z językiem, krajem, strefą czasową, motywem, bez danych demo (`--fixtures=0`); zapis losowego folderu panelu w `Shop.admin_path`; login (e-mail) i hasło pracownika | ~80 s |
| Waluta, koszyk i zamówienia | waluta (import z `localization/<kraj>.xml`, gdy jej nie ma), nazwa i e-mail sklepu, zakupy bez konta, stany magazynowe; wyłączenie płatności czekiem, przelewem i przy odbiorze oraz treści demo na stronie głównej (`ps_imageslider`, `ps_customtext`, `ps_banner`) | ~15 s |
| Kategorie produktów | kategorie pod „Strona główna” i opcjonalnie 6 przykładowych produktów (też na stronie głównej) | ~2 s |
| Menu, wyszukiwarka i filtry | menu górne z kategorii (`MOD_BLOCKTOPMENU_ITEMS`), szablon filtrów `ps_facetedsearch` (kategorie, cena, dostępność), indeks cen | ~3 s |
| Końcowe sprawdzenie | strona główna i strona logowania panelu (`/<folder>/login`) przez proxy, obie 200 | ~6 s |

Uwagi techniczne:

- **Panel** dostaje przy instalacji losową nazwę folderu (`admin` + znaki), co chroni go przed botami.
  Pracownik loguje się e-mailem; backend zapisuje go w `ShopCredentials.admin_login`.
- **Skrypty PHP** (`PrestaShopProvisioner._php`) ładują `config/config.inc.php` z kontekstem sklepu, języka i pierwszego
  superadministratora, jako `www-data`, żeby pliki pamięci podręcznej należały do serwera WWW. Każdy trwa ~1 s.
- **Waluta:** `new Currency()` zostawia pustą nazwę, symbol i format. Waluta musi przyjść z pakietu lokalizacji,
  a ten potrzebuje jądra Symfony panelu (`AdminKernel`), co kosztuje ~12 s. Dlatego jądro uruchamia tylko ten krok.
- **Motyw:** `bin/console prestashop:theme:enable` w 9.2 kończy się błędem kontekstu języka.
  Działa `ThemeManagerBuilder(...)->build()->enable()` i czyszczenie pamięci podręcznej.
- **Filtry:** `ps_facetedsearch::createDefaultTemplate()` tworzy szablon tylko z produktów z kombinacjami
  (łączy tabelę kombinacji przez `INNER JOIN`), więc przy prostych produktach nic nie powstaje. Szablon zapisujemy sami.
- **Adres** sklepu jest w tabeli `ps_shop_url` i w `PS_SHOP_DOMAIN`; `update_shop_addresses` podmienia oba
  i odtwarza `.htaccess`.
- **Braki:** logo „my store” z motywu zostaje do wymiany w panelu; część napisów motywu Hummingbird
  nie ma polskiego tłumaczenia („Search products…”, stopka).
