# Serwer sklepów

Tu działają sklepy WordPress + WooCommerce, każdy we własnym kontenerze.
Sklepy zakłada backend: worker Celery wykonuje kroki z
[docker_provisioner.py](../../backend/shops/provisioning/docker_provisioner.py) przez socket Dockera.
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
