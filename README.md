# Sklepownia

Platforma do automatycznego zakładania sklepów internetowych na WordPressie z WooCommerce.
Użytkownik zakłada konto, wypełnia krótki formularz (nazwa, adres, branża, motyw, język, waluta),
a platforma w około dwie minuty uruchamia działający sklep w osobnym kontenerze Dockera.

## Funkcje

- Konto użytkownika z potwierdzeniem adresu e-mail.
- Zakładanie sklepu z formularza: motyw (Storefront, Astra, Kadence), język, waluta, kraj,
  kategorie dobrane do branży i opcjonalnie przykładowe produkty.
- Podgląd postępu zakładania krok po kroku i ponowienie kroku, który się nie udał.
- Dane logowania do panelu WordPressa wysyłane e-mailem, nigdy pokazywane w aplikacji.
- Ustawienia sklepu (płatności, wysyłka, podatki, region, wygląd) zmieniane z aplikacji.
- Każdy sklep we własnym kontenerze, z własną bazą danych i adresem.
- Jedna aplikacja na iOS, Androida i przeglądarkę.
- Panel administratora z użytkownikami, sklepami i wiadomościami z formularza kontaktowego.

## Z czego składa się projekt

| Katalog | Co to jest | Technologie |
|---|---|---|
| [backend/](backend/) | API, konta, zakładanie sklepów, panel admina | Django 5.2, DRF, Celery, PostgreSQL, Redis |
| [mobile/](mobile/) | Aplikacja na iOS, Androida i przeglądarkę | Expo SDK 58, React Native 0.88, Expo Router |
| [infra/shops/](infra/shops/) | Serwer sklepów: proxy, baza sklepów, obraz WordPressa | Docker, Traefik 3, MariaDB 11, WordPress 7.1 |
| [docker-compose.yml](docker-compose.yml) | Lokalne uruchomienie backendu | Docker Compose |

## Szybki start

Wymagania: Docker z Compose, Node.js 20+ i npm. Szczegóły: [docs/uruchomienie.md](docs/uruchomienie.md).

```bash
# 1. Serwer sklepów
cd infra/shops && cp .env.example .env    # ustaw SHOPS_DB_ROOT_PASSWORD
docker compose build wordpress && docker compose up -d
cd ../..

# 2. Backend
cp .env.example .env                       # uzupełnij hasła i klucze, to samo SHOPS_DB_ROOT_PASSWORD
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser

# 3. Aplikacja
cd mobile && npm install && npx expo start
```

Po uruchomieniu:

| Adres | Co |
|---|---|
| http://localhost:8081 | Aplikacja w przeglądarce |
| http://localhost:8000/docs/ | Dokumentacja projektu jako strona |
| http://localhost:8000/api/docs/ | Dokumentacja endpointów API |
| http://localhost:8000/admin/ | Panel administratora |
| http://localhost:8030 | Poczta wysłana przez platformę (Mailpit): kody potwierdzające, dane logowania do sklepów |

## Dokumentacja

| Plik | O czym |
|---|---|
| [docs/architektura.md](docs/architektura.md) | Jak części systemu ze sobą współpracują, przebieg zakładania sklepu, stany sklepu |
| [docs/uruchomienie.md](docs/uruchomienie.md) | Lokalne środowisko krok po kroku, zmienne środowiskowe, podgląd na telefonie |
| [docs/backend.md](docs/backend.md) | Aplikacje Django, modele, provisioning, zadania Celery, testy, polecenia |
| [docs/api.md](docs/api.md) | Przegląd endpointów API i zasad uwierzytelniania |
| [docs/aplikacja-mobilna.md](docs/aplikacja-mobilna.md) | Ekrany, nawigacja, komponenty, wygląd, komunikacja z API |
| [infra/shops/README.md](infra/shops/README.md) | Serwer sklepów, kroki instalacji WordPressa, uwagi techniczne |
| [docs/obsluga.md](docs/obsluga.md) | Codzienna obsługa: zmiana sieci, restart, logi, typowe problemy |
| [docs/rozwoj.md](docs/rozwoj.md) | Sprawdzanie zmian, konwencje i utrzymanie dokumentacji |
| [docs/ograniczenia-i-plan.md](docs/ograniczenia-i-plan.md) | Czego jeszcze brakuje i co trzeba zrobić przed produkcją |

Przy działającym backendzie ta sama dokumentacja jest dostępna jako strona z menu pod http://localhost:8000/docs/.
Poza trybem deweloperskim (`DJANGO_DEBUG=0`) widzą ją tylko administratorzy.
