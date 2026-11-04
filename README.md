# Sklepownia

Aplikacja do automatycznego zakładania i prowadzenia sklepów internetowych na WordPressie z WooCommerce.
Użytkownik zakłada konto, wypełnia krótki formularz (nazwa, adres, branża, motyw, język, waluta),
a platforma w około dwie minuty stawia mu działający sklep w osobnym kontenerze Dockera.

„Sklepownia” to robocza nazwa, zdefiniowana w [mobile/src/constants/brand.ts](mobile/src/constants/brand.ts).

## Z czego składa się projekt

| Katalog | Co to jest | Technologie |
|---|---|---|
| [backend/](backend/) | API, konta, zakładanie sklepów, panel admina | Django 5.2, DRF, Celery, PostgreSQL, Redis |
| [mobile/](mobile/) | Aplikacja na iOS, Androida i przeglądarkę | Expo SDK 58, React Native 0.88, Expo Router |
| [infra/shops/](infra/shops/) | Serwer sklepów: proxy, baza sklepów, obraz WordPressa | Docker, Traefik 3, MariaDB 11, WordPress 7.1 |
| [docker-compose.yml](docker-compose.yml) | Lokalne uruchomienie backendu | Docker Compose |

## Szybki start

Wymagania: Docker z Compose, Node.js 20+ i npm. Szczegóły i rozwiązywanie problemów: [docs/uruchomienie.md](docs/uruchomienie.md).

```bash
# 1. Serwer sklepów (raz)
cd infra/shops && cp .env.example .env    # wpisz SHOPS_DB_ROOT_PASSWORD
docker compose build wordpress && docker compose up -d
cd ../..

# 2. Backend
cp .env.example .env                       # uzupełnij hasła, klucze i SHOPS_DB_ROOT_PASSWORD
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser

# 3. Aplikacja
cd mobile && npm install && npx expo start
```

- Aplikacja w przeglądarce: http://localhost:8081
- Ta dokumentacja jako strona: http://localhost:8000/docs/
- API i dokumentacja endpointów: http://localhost:8000/api/docs/
- Panel admina: http://localhost:8000/admin/

## Dokumentacja

Przy działającym backendzie całą dokumentację można czytać jako stronę z menu: http://localhost:8000/docs/.
Strona renderuje te same pliki Markdown na bieżąco, więc zmiana w pliku jest widoczna po odświeżeniu.
Bez trybu deweloperskiego (`DJANGO_DEBUG=0`) strona jest dostępna tylko dla administratorów.

| Plik | O czym |
|---|---|
| [docs/architektura.md](docs/architektura.md) | Jak części systemu ze sobą współpracują, przebieg zakładania sklepu, stany sklepu |
| [docs/uruchomienie.md](docs/uruchomienie.md) | Lokalne środowisko krok po kroku, zmienne środowiskowe, podgląd na telefonie |
| [docs/backend.md](docs/backend.md) | Aplikacje Django, modele, provisioning, zadania Celery, testy, polecenia |
| [docs/api.md](docs/api.md) | Przegląd endpointów API i zasad uwierzytelniania |
| [docs/aplikacja-mobilna.md](docs/aplikacja-mobilna.md) | Ekrany, nawigacja, komponenty, wygląd, komunikacja z API |
| [infra/shops/README.md](infra/shops/README.md) | Serwer sklepów, kroki instalacji WordPressa, wnioski z automatyzacji |
| [docs/obsluga.md](docs/obsluga.md) | Codzienna obsługa: zmiana sieci, restart, logi, typowe problemy |
| [docs/ograniczenia-i-plan.md](docs/ograniczenia-i-plan.md) | Czego jeszcze brakuje, znane problemy, droga do produkcji |

## Utrzymanie dokumentacji

Dokumentacja to zwykłe pliki Markdown w repozytorium i zmienia się razem z kodem, w tym samym commicie.

- Nowa zmienna środowiskowa: dopisz ją do [.env.example](.env.example) z komentarzem i do tabeli w [docs/uruchomienie.md](docs/uruchomienie.md).
- Nowy endpoint: opisz go w [docs/api.md](docs/api.md). Pełny opis pól generuje się sam (`/api/docs/`) z serializerów i `@extend_schema`.
- Nowy krok zakładania sklepu: dopisz go do `BaseProvisioner.STEPS` i do tabeli w [infra/shops/README.md](infra/shops/README.md).
- Nowy ekran albo komponent współdzielony: dopisz go do [docs/aplikacja-mobilna.md](docs/aplikacja-mobilna.md).
- Rozwiązany problem z [docs/ograniczenia-i-plan.md](docs/ograniczenia-i-plan.md): usuń go stamtąd.
- Nowy plik dokumentacji: dopisz go do tabeli wyżej i do `PAGES` w [backend/handbook/pages.py](backend/handbook/pages.py),
  żeby pojawił się w menu strony `/docs/`. Test `test_every_listed_page_exists_in_the_repository` pilnuje,
  żeby każda pozycja menu miała swój plik.
