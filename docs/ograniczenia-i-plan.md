# Ograniczenia i plan

Stan na listopad 2026. Gdy coś z tej listy zostanie zrobione, usuń to stąd w tym samym commicie.

## Czego brakuje w funkcjach

- **E-maile sklepów:** platforma wysyła pocztę przez SMTP (lokalnie do Mailpit), ale sklepy WordPress nie mają
  skonfigurowanej poczty, więc nie wyślą klientom potwierdzeń zamówień.
- **Hasło w e-mailu:** dane logowania do panelu przychodzą zwykłym e-mailem. Bezpieczniejsze będzie logowanie
  jednym kliknięciem z aplikacji, bez przesyłania hasła.
- **Płatności i wysyłka** nie są konfigurowane. Właściciel robi to sam w panelu WooCommerce.
- **Logowanie do panelu sklepu jednym kliknięciem.** Teraz aplikacja pokazuje login i hasło administratora.
  Pomysł: wtyczka „must-use” w WordPressie i jednorazowe linki logowania wydawane przez backend.
- **Atrybuty produktów według branży** (rozmiar, kolor, materiał), żeby filtry w sklepie miały z czego filtrować.
- **Zawieszanie sklepów:** stan `suspended` jest w modelu, ale nic go nie ustawia ani nie zdejmuje.
- **Ustawienia sklepu w aplikacji** obejmują podstawy, zakupy, płatności przelewem i przy odbiorze, wysyłkę w kraju sklepu,
  jedną stawkę VAT, region i motyw. Brakuje płatności internetowych (Przelewy24, PayU, karty), logo i kolorów motywu,
  wysyłki za granicę oraz regulaminu i polityki prywatności.
- **Płatności za platformę, plany i limity**: limit sklepów to jedna liczba dla wszystkich (`SHOPS_MAX_PER_USER`).
- **Testy na urządzeniu:** testy aplikacji działają w Jest; zachowania zależne od urządzenia (przewijanie,
  klawiatura, animacje) sprawdza się ręcznie w Expo Go.
- **Zdjęcia w przykładowych produktach.** Produkty przykładowe nie mają zdjęć, więc nowy sklep pokazuje szare zaślepki.
- **Porady w innych językach.** Instrukcja logowania i porady podają polskie nazwy z panelu WordPressa,
  także dla sklepów założonych w innym języku.

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
5. **Poczta:** dostawca SMTP dla platformy (zmienne `EMAIL_*`, zamiast Mailpit) i dla sklepów, z rekordami SPF i DKIM domeny.
6. **Monitorowanie:** zdrowie sklepów, błędy zakładania, zajętość serwera (`Server.max_shops`).
7. **Wiele serwerów sklepów.** Model `Server` i krok przydziału serwera są gotowe, ale `DockerProvisioner`
   rozmawia tylko z lokalnym Dockerem.
8. **Aplikacja w sklepach z aplikacjami:** ikony, ekran startowy, nazwa w `app.json` i build przez EAS.
9. **Szybsze zakładanie.** Najwięcej czasu zajmuje start WP-CLI przy każdym poleceniu. Zgrupowanie konfiguracji
   w jednym `wp eval-file` i pakiety językowe wbudowane w obraz powinny skrócić zakładanie z około 105 s do około 30 s.
