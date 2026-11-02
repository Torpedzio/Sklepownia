# Serwer sklepów (etap 2: ręczny prototyp)

Tu działają sklepy WordPress + WooCommerce, każdy we własnym kontenerze.
Na razie sklepy zakłada się skryptem. W etapie 3 te same kroki wykona backend
(`DockerProvisioner` zamiast `FakeProvisioner`).

```
przeglądarka ──▶ Traefik :8080 ──Host: <slug>.localhost──▶ kontener shop-<slug> (WordPress + WooCommerce)
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

Porty 80/443 zajmuje u nas `ddev-router`, dlatego sklepy są na **8080**.
Przeglądarki i curl same rozwiązują `*.localhost` na 127.0.0.1, więc nie trzeba konfigurować DNS.
Telefon tak nie potrafi; do testów z telefonu wystarczy później `SHOPS_DOMAIN=<ip-z-myślnikami>.sslip.io`.

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

Kroki odpowiadają `BaseProvisioner.STEPS` w backendzie. Czasy pochodzą z czystej instalacji na laptopie.

| Krok | Co robi | Czas |
|---|---|---|
| Tworzenie bazy danych | `CREATE DATABASE/USER` w MariaDB, osobne hasło na sklep | ~0 s |
| Uruchamianie WordPressa | `docker run` z etykietami Traefika i limitami 512 MB / 1 CPU; czekanie na `wp-config.php` | ~5 s |
| Instalacja WordPressa | `wp core install`, usunięcie domyślnych wpisów, stron i widgetów | ~4 s |
| Ustawienia języka i regionu | pakiet językowy, strefa czasowa z kraju, permalinki `/%postname%/` | ~8 s |
| Konfiguracja WooCommerce | tłumaczenie → aktywacja → waluta, format cen, jednostki, e-mail; wyłączenie trybu „coming soon” i kreatora; strony sklepu; sklep jako strona główna | ~30 s |
| Instalacja motywu | aktywacja motywu z obrazu i jego tłumaczenie | ~5 s |
| Tworzenie kategorii | kategorie i opcjonalnie 6 przykładowych produktów | ~25 s |
| Generowanie kluczy API | Application Password `platform` dla admina | ~3 s |
| Sprawdzanie działania sklepu | strona główna 200 i `wc/v3/system_status` z hasłem API | ~4 s |
| **Razem** | | **~90 s** |

## Wnioski do etapu 3

- **Każdy krok jest idempotentny.** Ponowne uruchomienie dla tego samego sluga dokańcza sklep.
  Hasło admina jest jednak generowane tylko przy pierwszej instalacji, więc backend musi je zapisać
  w `ShopCredentials` **zanim** wykona dalsze kroki.
- **Kolejność ma znaczenie:** tłumaczenie WooCommerce trzeba zainstalować **przed** aktywacją wtyczki,
  bo aktywacja tworzy strony sklepu w aktywnym języku. W odwrotnej kolejności powstają „Cart” i „Checkout”.
- **WooCommerce 11:** opcja `woocommerce_task_list_hidden` jest martwa (`wp option update` zwraca błąd).
  Zastępuje ją `woocommerce_task_list_hidden_lists`. Nowe sklepy startują w trybie „coming soon”,
  który trzeba wyłączyć (`woocommerce_coming_soon=no`).
- **Klucze API:** zamiast kluczy WooCommerce (`ck_`/`cs_`, których nie da się wygenerować z WP-CLI)
  używamy Application Password. WooCommerce REST API przyjmuje go przez Basic Auth.
  Przez HTTP działa tylko przy `WP_ENVIRONMENT_TYPE=local`; na produkcji potrzebny jest HTTPS.
  Do zmiany w modelu: `wc_consumer_key/secret` w `ShopCredentials` są zbędne.
- **Czas:** najwięcej kosztuje start WP-CLI przy każdym poleceniu (~1–2 s). Zgrupowanie konfiguracji
  WooCommerce i kategorii w jednym `wp eval-file` powinno skrócić całość do ~30 s.
  Pakiety językowe też można wbudować w obraz.
- **Nazwy kategorii:** backend będzie musiał je wymyślić na podstawie branży i liczby kategorii.
  Skrypt przyjmuje gotową listę.
- **Dostęp do Dockera:** Traefik czyta `docker.sock` (na Fedorze z `label=disable` przez SELinux).
  Worker backendu będzie potrzebował tego samego, dlatego w etapie 4 trzeba go odseparować.
