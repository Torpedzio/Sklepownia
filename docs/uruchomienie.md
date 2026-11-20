# Uruchomienie lokalne

## Wymagania

- Docker z Docker Compose (na systemach z SELinux, np. Fedorze, też działa)
- Node.js 20+ i npm (projekt rozwijany na Node 22)
- Wolny port 8000 (API), 8080 (sklepy) i 8081 (Metro, serwer aplikacji)
- Na telefonie: aplikacja Expo Go w wersji obsługującej SDK 58

## 1. Serwer sklepów

Potrzebny tylko przy `SHOP_PROVISIONER=docker`. Z symulacją (`FakeProvisioner`) można go pominąć.

```bash
cd infra/shops
cp .env.example .env               # wpisz SHOPS_DB_ROOT_PASSWORD
docker compose build wordpress magento   # obrazy sklepów WooCommerce i Magento (Magento ~10 min)
docker compose build backup              # kopie zapasowe sklepów (restic)
docker compose up -d                     # Traefik (shops-proxy), MariaDB (shops-db), OpenSearch (shops-search)
```

Szczegóły: [infra/shops/README.md](../infra/shops/README.md).

## 2. Backend

```bash
cp .env.example .env
# uzupełnij: DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEY, SHOPS_DB_ROOT_PASSWORD (to samo co w infra/shops/.env)
# i SHOPS_BACKUP_PASSWORD (bez niego sklepy nie mają kopii zapasowych)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FIELD_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"                                # SHOPS_BACKUP_PASSWORD

docker compose up -d                                   # db, redis, backend, worker, beat, mail
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser   # konto do panelu /admin/
```

Migracje dodają też szablony sklepów (Storefront, Astra, Kadence) i serwer `local`.

| Adres | Co |
|---|---|
| http://localhost:8000/api/health/ | Sprawdzenie, czy API działa |
| http://localhost:8000/docs/ | Dokumentacja projektu (te pliki jako strona) |
| http://localhost:8000/api/docs/ | Dokumentacja API (Swagger) |
| http://localhost:8000/admin/ | Panel admina Django |
| http://localhost:8030 | Mailpit: cała poczta wysłana przez platformę (nic nie wychodzi na zewnątrz) |
| http://localhost:8031 | Mailpit serwera sklepów: poczta wysłana przez sklepy |

Backend działa na `runserver` z katalogiem `backend/` podmontowanym do kontenera, więc zmiany w kodzie
przeładowują się same. Worker Celery **nie** przeładowuje się sam: po zmianie kodu provisioningu
uruchom `docker compose restart worker`.

## 3. Aplikacja

```bash
cd mobile
npm install
npx expo start
```

- `w` w terminalu albo http://localhost:8081 otwiera wersję w przeglądarce.
- Kod QR w terminalu otwiera aplikację w Expo Go (Android: skaner w Expo Go, iPhone: aparat systemowy).

Adres API aplikacja wylicza sama z adresu Metro (`http://<host>:8000/api`). Inny adres można wymusić
zmienną `EXPO_PUBLIC_API_URL`.

## Podgląd na telefonie

1. Telefon i komputer w tej samej sieci Wi-Fi. Test: `http://<IP-komputera>:8081/status` w przeglądarce telefonu
   powinien pokazać `packager-status:running`.
2. Sklepy muszą mieć domenę widoczną z telefonu, bo `localhost` na telefonie to sam telefon:
   ```bash
   # w .env, z IP komputera zapisanym myślnikami
   SHOPS_BASE_DOMAIN=192-168-1-20.sslip.io
   docker compose up -d backend worker
   docker compose exec worker python manage.py update_shop_addresses
   ```
3. Po zmianie sieci powtórz punkt 2 z nowym IP i zeskanuj nowy kod QR
   (albo wpisz w Expo Go `exp://<IP>:8081`). Więcej: [obsluga.md](obsluga.md#zmiana-sieci-lub-adresu-ip).

## Powiadomienia push

W Expo Go i w przeglądarce powiadomienia nie działają (Expo Go na Androidzie nie ma ich od SDK 53).
Ekran „Powiadomienia” mówi wtedy, dlaczego. Żeby je sprawdzić na telefonie:

1. Konto Expo i projekt EAS: `cd mobile && npx eas-cli@latest init`. Dopisuje `extra.eas.projectId` do konfiguracji,
   bez którego aplikacja nie dostanie tokenu.
2. Klucze: dla Androida plik `google-services.json` z projektu Firebase i klucz FCM V1 wgrany przez
   `npx eas-cli@latest credentials`; dla iOS klucz APNs utworzy EAS przy pierwszym buildzie.
3. Build deweloperski: `npx eas-cli@latest build --profile development --platform android` (albo `ios`), instalacja
   na telefonie, potem `npx expo start` jak zwykle.
4. W aplikacji: Konto → Powiadomienia → „Włącz powiadomienia”. Telefon pojawi się na liście pod przełącznikami.

Backend wysyła przez Expo Push bez dodatkowej konfiguracji. `EXPO_ACCESS_TOKEN` jest potrzebny tylko z włączonym
„Enhanced Security for Push Notifications” w projekcie Expo. Bez telefonu można podejrzeć treść powiadomień
w logu workera: `PUSH_SENDER=push.senders.log.LogSender` w `.env` i `docker compose restart worker`.

## Poczta w środowisku lokalnym

Lokalnie całą pocztę przyjmuje Mailpit (usługa `mail` w [docker-compose.yml](../docker-compose.yml)) i nic nie wychodzi
na zewnątrz. Wiadomości czyta się w przeglądarce: http://localhost:8030. Trafiają tam kody potwierdzające e-mail,
dane logowania do sklepów i wiadomości z formularza kontaktowego.

Port 8030 wybrany jest dlatego, że 8025 często zajmuje inny Mailpit (np. z DDEV). Inny port: `MAIL_UI_PORT` w `.env`.

Pocztę sklepów (potwierdzenia zamówień, e-maile kont klientów, powiadomienia właściciela o zamówieniach) przyjmuje
osobny Mailpit na serwerze sklepów: usługa `mail` w [infra/shops/docker-compose.yml](../infra/shops/docker-compose.yml),
podgląd http://localhost:8031 (port: `SHOPS_MAIL_UI_PORT` w `infra/shops/.env`). Jest osobny, bo sklepy mogą
odczytać wszystko, z czym rozmawiają, a w poczcie platformy są kody i hasła innych sklepów.
Bez ustawień poczty w `.env` backend wypisuje wiadomości w logach (`EMAIL_BACKEND` domyślnie to backend konsolowy):
`docker compose logs worker`.

## Zmienne środowiskowe (`.env`)

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | — (wymagane) | Baza aplikacji |
| `POSTGRES_HOST`, `POSTGRES_PORT` | `db`, `5432` | Adres bazy |
| `DJANGO_SECRET_KEY` | — (wymagane) | Klucz Django |
| `DJANGO_DEBUG` | `0` | `1` w środowisku deweloperskim |
| `DJANGO_ALLOWED_HOSTS` | `localhost` | Lista po przecinku; lokalnie `*`, bo IP w sieci się zmienia |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:8081` | Skąd przeglądarka może wołać API (wersja web) |
| `REDIS_URL` | `redis://redis:6379/0` | Kolejka Celery |
| `FIELD_ENCRYPTION_KEY` | — (wymagane) | Klucz Fernet do szyfrowania haseł sklepów. **Zmiana klucza = utrata dostępu do zapisanych haseł.** |
| `EMAIL_BACKEND` | konsola | Lokalnie `django.core.mail.backends.smtp.EmailBackend` (Mailpit) |
| `EMAIL_HOST`, `EMAIL_PORT` | `localhost`, `25` | Serwer SMTP; lokalnie `mail`, `1025` |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | puste, `0` | Logowanie i szyfrowanie u dostawcy poczty na produkcji |
| `DEFAULT_FROM_EMAIL` | `Sklepownia <no-reply@localhost>` | Nadawca wiadomości |
| `PLATFORM_NAME` | `Sklepownia` | Nazwa platformy w treści wiadomości |
| `APP_URL` | `http://localhost:8081` | Adres aplikacji w wersji web, do którego prowadzą linki w wiadomościach (zaproszenia do zespołu) |
| `MAIL_UI_PORT` | `8030` | Port podglądu Mailpit (tylko docker-compose) |
| `SHOPS_SMTP_HOST`, `SHOPS_SMTP_PORT` | `shops-mail`, `1025` | Przekaźnik poczty sklepów w sieci serwera sklepów, bez logowania. Puste `SHOPS_SMTP_HOST`: sklepy bez poczty |
| `SHOPS_MAIL_DOMAIN` | `SHOPS_BASE_DOMAIN` | Sklepy wysyłają jako `<slug>@<domena>`; domena musi mieć kropkę (dla `localhost`: `sklepy.localhost`) |
| `PAYMENT_GATEWAY` | `FakeGateway` | Symulowana bramka albo `billing.gateways.tpay.TpayGateway` ([platnosci.md](platnosci.md#operatorzy-płatności)) |
| `TPAY_CLIENT_ID`, `TPAY_CLIENT_SECRET` | puste | Klucze Open API z panelu Tpay |
| `TPAY_SECURITY_CODE` | puste | Kod bezpieczeństwa powiadomień (panel Tpay → Powiadomienia → Bezpieczeństwo) |
| `TPAY_SANDBOX` | `1` | `1` = środowisko testowe Tpay, `0` = produkcja |
| `TPAY_NOTIFICATION_URL` | `http://localhost:8000/api/billing/notifications/` | Publiczny adres powiadomień o płatnościach |
| `BILLING_RETURN_URL_PREFIXES` | `http://localhost:8081/,mobile://,exp://` | Dokąd operator może odesłać płacącego |
| `FAKE_GATEWAY_DECLINE_RENEWALS` | `0` | `1` = symulowana bramka odrzuca odnowienia (test nieudanych płatności) |
| `PUSH_SENDER` | `push.senders.expo.ExpoSender` | Wysyłka powiadomień push: Expo albo `push.senders.log.LogSender` (tylko log workera) |
| `EXPO_ACCESS_TOKEN` | puste | Token dostępu Expo, gdy projekt wymaga go przy wysyłce push |
| `CONTACT_EMAIL` | `kontakt@localhost` | Dokąd trafiają wiadomości z formularza kontaktowego |
| `HANDBOOK_ROOT` | `/project` | Katalog repozytorium w kontenerze, z którego strona `/docs/` czyta dokumentację |
| `SHOP_PROVISIONER` | `FakeProvisioner` | Symulacja albo prawdziwe sklepy ([architektura.md](architektura.md#provisionery)) |
| `SHOPS_BASE_DOMAIN` | `localhost` | Domena sklepów: `<slug>.<domena>` |
| `SHOPS_URL_SCHEME`, `SHOPS_HTTP_PORT` | `https`, `443` | Lokalnie `http` i `8080` |
| `SHOPS_WP_ENVIRONMENT` | `production` | `local` pozwala na hasła API WordPressa przez HTTP |
| `SHOPS_DB_ROOT_PASSWORD` | — | Hasło roota MariaDB sklepów, to samo co w `infra/shops/.env` |
| `SHOPS_WORDPRESS_IMAGE`, `SHOPS_PRESTASHOP_IMAGE`, `SHOPS_MAGENTO_IMAGE` | `shops/wordpress:7.1`, `prestashop/prestashop:9.2.1-apache`, `shops/magento:4.0.0` | Obrazy kontenerów sklepów |
| `SHOPS_NETWORK` | `shops` | Sieć Dockera serwera sklepów |
| `SHOPS_DB_CONTAINER`, `SHOPS_PROXY_CONTAINER`, `SHOPS_SEARCH_CONTAINER` | `shops-db`, `shops-proxy`, `shops-search` | Nazwy kontenerów serwera sklepów |
| `SHOPS_CONTAINER_MEMORY` | `512m` | Limit pamięci kontenera sklepu bez planu i sklepu testowego |
| `SHOPS_MAGENTO_MEMORY` | `1536m` | Najmniejszy limit pamięci sklepu Magento, niezależnie od planu |
| `SHOPS_PACKAGE_CACHE` | `/tmp/sklepownia-packages` | Folder workera na pobrane wtyczki płatności (sprawdzane sumą SHA-256, pobierane raz) |
| `SHOPS_BACKUP_PASSWORD` | puste | Hasło repozytorium kopii zapasowych sklepów. Puste: kopie wyłączone. **Bez niego kopii nie da się odczytać**, więc jego kopia musi być też poza serwerem |
| `SHOPS_BACKUP_HOUR` | `3` | Godzina nocnych kopii (czas polski) |
| `SHOPS_BACKUP_KEEP_DAILY`, `SHOPS_BACKUP_KEEP_WEEKLY` | `7`, `4` | Z ilu ostatnich dni i tygodni zostaje po jednej kopii (oprócz wszystkich z ostatniej doby) |
| `SHOPS_BACKUP_DELETED_DAYS` | `14` | Ile dni zostaje ostatnia kopia usuniętego sklepu |
| `SHOPS_BACKUP_MANUAL_PER_DAY` | `3` | Ile kopii dziennie właściciel może zrobić sam |
| `SHOPS_BACKUP_IMAGE`, `SHOPS_BACKUP_VOLUME`, `SHOPS_BACKUP_CACHE_VOLUME` | `shops/backup:0.19.1`, `shops-backups`, `shops-backup-cache` | Obraz narzędzia kopii, wolumen repozytorium i wolumen pamięci podręcznej restic |
| `MONITOR_INTERVAL_MINUTES` | `5` | Co ile minut monitor sprawdza sklepy i serwer sklepów ([monitorowanie](obsluga.md#monitorowanie)) |
| `MONITOR_FAILURES` | `2` | Po ilu nieudanych sprawdzeniach z rzędu sklep nie działa (restart, potem powiadomienia) |
| `ALERT_EMAILS` | `CONTACT_EMAIL` | Adresy obsługi (po przecinku) na alarmy monitora |
| `MONITOR_DISK_MIN_FREE_PERCENT`, `MONITOR_SERVER_FULL_PERCENT` | `10`, `90` | Alarm przy mniej wolnego miejsca na dysku serwera sklepów i przy takim zapełnieniu serwera (`Server.max_shops`) |
| `MONITOR_PING_URL` | puste | Adres pingowany po każdej rundzie (np. Healthchecks.io), który alarmuje, gdy monitor przestanie działać |
| `MONITOR_WORKERS` | `8` | Ile sklepów naraz sprawdza runda |
| `FAKE_PROVISIONER_STEP_DELAY` | `2` | Sekundy na krok w symulacji |
| `FAKE_PROVISIONER_FAIL_AT_STEP` | puste | Klucz kroku, na którym symulacja ma się wysypać |

Aplikacja mobilna: `EXPO_PUBLIC_API_URL` (opcjonalnie) wymusza adres API. `SITE_URL` (tylko serwer strony,
bez `EXPO_PUBLIC_`) to adres strony w linkach kanonicznych, podglądach linków i `sitemap.xml`; bez niego serwer
bierze adres z zapytania, co lokalnie wystarcza, ale za proxy na produkcji da adres wewnętrzny.

## Sprawdzanie zmian

```bash
docker compose exec backend pytest                        # testy backendu
docker compose exec backend python manage.py spectacular --validate --fail-on-warn > /dev/null   # schemat API
cd mobile && npx tsc --noEmit && npx expo lint && npm test   # typy, lint i testy aplikacji
```

