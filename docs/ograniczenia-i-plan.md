# Ograniczenia i plan

Stan na listopad 2026. Gdy coś z tej listy zostanie zrobione, usuń to stąd w tym samym commicie.

## Znane problemy

- **Storefront traci pasek boczny.** W jednym sklepie widżety (kategorie, filtry) zniknęły z paska bocznego,
  choć ich dane zostały w bazie. Sprawdzone: przenoszenie adresów nie jest przyczyną.
  Podejrzenie: WordPress przestawia widżety po zmianie motywu przez WP-CLI, przy pierwszym wejściu do panelu.
  Do zbadania na świeżo założonym sklepie ze Storefront.
- **Produkty przykładowe nie mają zdjęć.** Sklep po założeniu i podglądy motywów pokazują szare zaślepki.
- **Instrukcja logowania i porady podają polskie nazwy z panelu WordPressa**, także dla sklepów w innym języku.
- **Dane marki są tymczasowe:** nazwa, e-mail, telefon i adres w `mobile/src/constants/brand.ts`.
- **Zdjęcia na stronie głównej:** przed publikacją trzeba sprawdzić prawa do zdjęć z katalogu `images/`.
- **Lint aplikacji** zgłasza błąd w szablonowym pliku `mobile/src/hooks/use-color-scheme.web.ts`.

## Czego brakuje w funkcjach

- **E-maile:** platforma ani sklepy nie wysyłają prawdziwych e-maili (brak SMTP).
  Kody potwierdzające są tylko w logach, a sklepy nie wyślą klientom potwierdzeń zamówień.
- **Płatności i wysyłka** nie są konfigurowane. Właściciel robi to sam w panelu WooCommerce.
- **Logowanie do panelu sklepu jednym kliknięciem.** Teraz aplikacja pokazuje login i hasło administratora.
  Pomysł: wtyczka „must-use” w WordPressie i jednorazowe linki logowania wydawane przez backend.
- **Atrybuty produktów według branży** (rozmiar, kolor, materiał), żeby filtry w sklepie miały z czego filtrować.
- **Zawieszanie sklepów:** stan `suspended` jest w modelu, ale nic go nie ustawia ani nie zdejmuje.
- **Zmiana ustawień sklepu z aplikacji** (motyw, język, waluta). Dziś tylko przez panel WordPressa.
- **Płatności za platformę, plany i limity**: limit sklepów to jedna liczba dla wszystkich (`SHOPS_MAX_PER_USER`).
- **Testy aplikacji mobilnej:** są tylko testy backendu.

## Droga do produkcji

Projekt działa dziś tylko lokalnie. Przed uruchomieniem dla użytkowników trzeba:

1. **Domena i HTTPS.** Prawdziwa domena z wieloznacznym rekordem DNS (`*.sklepy.example.pl`) i certyfikatem
   wildcard w Traefiku (Let's Encrypt, wyzwanie DNS). Potem `SHOPS_URL_SCHEME=https`, `SHOPS_WP_ENVIRONMENT=production`.
2. **Bezpieczny dostęp do Dockera.** Worker ma dziś surowy socket Dockera, czyli uprawnienia roota.
   Trzeba go odseparować, np. przez proxy socketu ograniczające dozwolone operacje
   albo osobny agent na serwerze sklepów z własnym API.
3. **Serwer aplikacji.** Gunicorn lub uvicorn zamiast `runserver`, `DJANGO_DEBUG=0`, konkretne `DJANGO_ALLOWED_HOSTS`
   i `CORS_ALLOWED_ORIGINS`, pliki statyczne, kopie zapasowe PostgreSQL.
4. **Kopie zapasowe sklepów:** wolumenów WordPressa i baz MariaDB.
5. **SMTP** dla platformy i sklepów.
6. **Monitorowanie:** zdrowie sklepów, błędy zakładania, zajętość serwera (`Server.max_shops`).
7. **Wiele serwerów sklepów.** Model `Server` i krok przydziału serwera są gotowe, ale `DockerProvisioner`
   rozmawia tylko z lokalnym Dockerem.
8. **Aplikacja w sklepach z aplikacjami:** ikony, ekran startowy, nazwa w `app.json` i build przez EAS.
9. **Szybsze zakładanie.** Najwięcej czasu zajmuje start WP-CLI przy każdym poleceniu. Zgrupowanie konfiguracji
   w jednym `wp eval-file` i pakiety językowe wbudowane w obraz powinny skrócić zakładanie z około 105 s do około 30 s.
