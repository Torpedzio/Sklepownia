# Uruchomienie lokalne

## Wymagania

- Docker z Docker Compose (testowane na Fedorze z SELinux)
- Node.js 20+ i npm (projekt rozwijany na Node 22)
- Wolny port 8000 (API), 8080 (sklepy) i 8081 (Metro, serwer aplikacji)
- Na telefonie: aplikacja Expo Go w wersji obsługującej SDK 58

## 1. Serwer sklepów

Potrzebny tylko przy `SHOP_PROVISIONER=...DockerProvisioner`. Z symulacją (`FakeProvisioner`) można go pominąć.

```bash
cd infra/shops
cp .env.example .env               # wpisz SHOPS_DB_ROOT_PASSWORD
docker compose build wordpress     # obraz sklepu: WordPress + WP-CLI + WooCommerce + motywy
docker compose up -d               # Traefik (shops-proxy) i MariaDB (shops-db)
```

Szczegóły: [infra/shops/README.md](../infra/shops/README.md).

## 2. Backend

```bash
cp .env.example .env
# uzupełnij: DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEY, SHOPS_DB_ROOT_PASSWORD (to samo co w infra/shops/.env)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FIELD_ENCRYPTION_KEY

docker compose up -d                                   # db, redis, backend, worker
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
   SHOPS_BASE_DOMAIN=192-168-33-10.sslip.io
   docker compose up -d backend worker
   docker compose exec worker python manage.py update_shop_addresses
   ```
3. Po zmianie sieci powtórz punkt 2 z nowym IP i zeskanuj nowy kod QR
   (albo wpisz w Expo Go `exp://<IP>:8081`). Więcej: [obsluga.md](obsluga.md#zmiana-sieci-lub-adresu-ip).

## Potwierdzenie e-maila w środowisku lokalnym

Lokalnie e-maile nie są wysyłane, tylko wypisywane w logach (`EMAIL_BACKEND` domyślnie to backend konsolowy).
Wysyłka idzie przez Celery, więc kod potwierdzający jest w logach workera:

```bash
docker compose logs worker | grep -A2 "kod weryfikacyjny"
```

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
| `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` | konsola, `no-reply@localhost` | Wysyłka e-maili |
| `CONTACT_EMAIL` | `kontakt@localhost` | Dokąd trafiają wiadomości z formularza kontaktowego |
| `HANDBOOK_ROOT` | `/project` | Katalog repozytorium w kontenerze, z którego strona `/docs/` czyta dokumentację |
| `SHOP_PROVISIONER` | `FakeProvisioner` | Symulacja albo prawdziwe sklepy ([architektura.md](architektura.md#provisionery)) |
| `SHOPS_MAX_PER_USER` | `3` | Limit sklepów na konto |
| `SHOPS_BASE_DOMAIN` | `localhost` | Domena sklepów: `<slug>.<domena>` |
| `SHOPS_URL_SCHEME`, `SHOPS_HTTP_PORT` | `https`, `443` | Lokalnie `http` i `8080` |
| `SHOPS_WP_ENVIRONMENT` | `production` | `local` pozwala na hasła API WordPressa przez HTTP |
| `SHOPS_DB_ROOT_PASSWORD` | — | Hasło roota MariaDB sklepów, to samo co w `infra/shops/.env` |
| `SHOPS_WORDPRESS_IMAGE` | `shops/wordpress:7.1` | Obraz kontenera sklepu |
| `SHOPS_NETWORK` | `shops` | Sieć Dockera serwera sklepów |
| `SHOPS_DB_CONTAINER`, `SHOPS_PROXY_CONTAINER` | `shops-db`, `shops-proxy` | Nazwy kontenerów serwera sklepów |
| `SHOPS_CONTAINER_MEMORY` | `512m` | Limit pamięci kontenera sklepu |
| `FAKE_PROVISIONER_STEP_DELAY` | `2` | Sekundy na krok w symulacji |
| `FAKE_PROVISIONER_FAIL_AT_STEP` | puste | Klucz kroku, na którym symulacja ma się wysypać |

Aplikacja mobilna: `EXPO_PUBLIC_API_URL` (opcjonalnie) wymusza adres API.

## Sprawdzanie zmian

```bash
docker compose exec backend pytest                        # testy backendu
docker compose exec backend python manage.py spectacular --validate --fail-on-warn > /dev/null   # schemat API
cd mobile && npx tsc --noEmit && npx expo lint            # typy i lint aplikacji
```

Lint zgłasza jeden znany błąd w pliku z szablonu Expo: `src/hooks/use-color-scheme.web.ts`.
