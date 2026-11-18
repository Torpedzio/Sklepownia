# Ograniczenia i plan

Stan na listopad 2026. Gdy coś z tej listy zostanie zrobione, usuń to stąd w tym samym commicie.

## Czego brakuje w funkcjach

- **Hasło w e-mailu:** dane logowania do panelu przychodzą zwykłym e-mailem. Bezpieczniejsze będzie logowanie
  jednym kliknięciem z aplikacji, bez przesyłania hasła.
- **Płatności i wysyłka** nie są konfigurowane. Właściciel robi to sam w panelu WooCommerce.
- **Logowanie do panelu sklepu jednym kliknięciem.** Teraz aplikacja pokazuje login i hasło administratora.
  Pomysł: wtyczka „must-use” w WordPressie i jednorazowe linki logowania wydawane przez backend.
- **Atrybuty produktów według branży** (rozmiar, kolor, materiał), żeby filtry w sklepie miały z czego filtrować.
- **Ustawienia sklepu w aplikacji** obejmują podstawy, zakupy, płatności przelewem i przy odbiorze, wysyłkę w kraju sklepu,
  jedną stawkę VAT, region i motyw. Brakuje płatności internetowych (Przelewy24, PayU, karty), logo i kolorów motywu,
  wysyłki za granicę oraz regulaminu i polityki prywatności.
- **Płatności, dalsze etapy** ([platnosci.md](platnosci.md)):
  - zawieszanie sklepów (stan `suspended`), gdy plan wygaśnie lub zostanie anulowany, i usuwanie po okresie przechowania;
  - zmiana karty z aplikacji (nowa płatność z zapisaniem karty);
  - strona „Sklep niedostępny” pod adresem zawieszonego sklepu (dziś proxy odpowiada 404);
  - faktury korygujące (np. przy zwrocie) i własne połączenie z KSeF bez Fakturowni;
  - regulamin i polityka prywatności jako strony, do których prowadzą zgody przy płatności;
  - zniżki, okresy próbne, plany roczne, inne metody płatności (BLIK, przelew), wypłata salda przy rezygnacji.
- **Sprzedaż w aplikacji** jest tylko do podglądu: zamówienia obsługuje się w panelu sklepu. Kopia obejmuje 90 dni,
  sumy liczą tylko walutę sklepu, a nowe zamówienie pojawia się w aplikacji z opóźnieniem do 15 minut (od razu po
  „Odśwież”). Brakuje zestawień dłuższych niż 30 dni.
- **Powiadomienia push** o nowym zamówieniu przychodzą przy odczycie sklepu, więc do 15 minut po złożeniu.
  Od razu dawałby je webhook sklepu (WooCommerce `order.created`) wołający platformę. Aplikacja nie ma jeszcze
  projektu EAS ani kluczy FCM i APNs, więc powiadomienia działają dopiero po ich dodaniu i w buildzie, nie w Expo Go.
  Brakuje powiadomień o niskim stanie magazynu.
- **Lista startowa** odhacza tylko to, co platforma widzi: ustawień robionych w panelu sklepu (np. wysyłki
  w PrestaShop, logo, danych firmy) nie sprawdza i ich nie pokazuje. Ustawienia zmienione w panelu odhaczają się po
  otwarciu ustawień w aplikacji, które czyta je ze sklepu. Krok powiadomień wymaga buildu aplikacji (patrz niżej).
  Ukrytej listy nie da się jeszcze przywrócić z aplikacji (API to umie: `PATCH … {hidden: false}`).
- **Testy na urządzeniu:** testy aplikacji działają w Jest; zachowania zależne od urządzenia (przewijanie,
  klawiatura, animacje) sprawdza się ręcznie w Expo Go.
- **Zdjęcia w przykładowych produktach.** Produkty przykładowe nie mają zdjęć, więc nowy sklep pokazuje szare zaślepki.
- **Porady w innych językach.** Instrukcja logowania i porady podają polskie nazwy z panelu WordPressa,
  także dla sklepów założonych w innym języku.

## Inne platformy sklepów

Działają WooCommerce, PrestaShop i Magento ([architektura.md](architektura.md#platformy-sklepów)). Kandydaci na kolejne:

| System | Jak by działał | Uwagi |
|---|---|---|
| Shopware 6 | własny kontener | obraz bazowy wymaga zbudowania projektu przez Composer; popularny w Niemczech |
| Sylius | własny kontener | framework na Symfony, bardziej dla programistów niż małych firm |
| OpenCart | własny kontener | lekki i prosty, mniejszy ekosystem |
| Shoper, IdoSell, Sky-Shop | konto u dostawcy przez API partnerskie | SaaS: sklepu nie da się postawić u nas; potrzebna umowa partnerska, a sklep i płatność za niego są u dostawcy |
| Shopify, BigCommerce | jw. | jw.; Shopify ma program partnerski i sklepy rozwojowe |

W PrestaShop aplikacja nie zmienia jeszcze zakupów (konto klienta, opinie, stany), wysyłki, podatków ani regionu.
Właściciel ustawia je w panelu. Zmiana języka po założeniu sklepu wymagałaby pobrania pakietu językowego i tłumaczenia kategorii.

W Magento aplikacja nie zamyka sklepu (Magento nie ma trybu „wkrótce otwarcie” bez dodatkowego modułu), nie zmienia
zakupów ani motywu. Magento dostaje co najmniej 1,5 GB pamięci także przy planach, które dają mniej.

## Droga do produkcji

Projekt działa dziś tylko lokalnie. Przed uruchomieniem dla użytkowników trzeba:

1. **Domena i HTTPS.** Prawdziwa domena z wieloznacznym rekordem DNS (`*.sklepy.example.pl`) i certyfikatem
   wildcard w Traefiku (Let's Encrypt, wyzwanie DNS). Potem `SHOPS_URL_SCHEME=https`, `SHOPS_WP_ENVIRONMENT=production`.
2. **Bezpieczny dostęp do Dockera.** Worker ma dziś surowy socket Dockera, czyli uprawnienia roota.
   Trzeba go odseparować, np. przez proxy socketu ograniczające dozwolone operacje
   albo osobny agent na serwerze sklepów z własnym API.
3. **Serwer aplikacji.** Gunicorn lub uvicorn zamiast `runserver`, `DJANGO_DEBUG=0`, konkretne `DJANGO_ALLOWED_HOSTS`
   i `CORS_ALLOWED_ORIGINS`, pliki statyczne, kopie zapasowe PostgreSQL.
4. **Kopie zapasowe sklepów:** wolumenów sklepów i baz MariaDB (indeksy OpenSearch da się odbudować `indexer:reindex`).
5. **Poczta:** dostawca SMTP dla platformy (zmienne `EMAIL_*`, zamiast Mailpit) z rekordami SPF i DKIM domeny.
   Dla sklepów przekaźnik na serwerze sklepów w miejsce `shops-mail` (np. Postfix), który trzyma dane logowania
   do dostawcy i przepuszcza tylko nadawców z `SHOPS_MAIL_DOMAIN`, z limitem wiadomości na sklep. Domena
   `SHOPS_MAIL_DOMAIN` potrzebuje SPF i DKIM, a poczta przychodząca na `<slug>@` najlepiej przekierowana
   do właściciela, gdyby ktoś odpisał na adres nadawcy zamiast na Reply-To.
6. **Monitorowanie:** zdrowie sklepów, błędy zakładania, zajętość serwera (`Server.max_shops`).
7. **Wiele serwerów sklepów.** Model `Server` i krok przydziału serwera są gotowe, ale provisionery
   rozmawiają tylko z lokalnym Dockerem.
8. **Aplikacja w sklepach z aplikacjami:** ikony, ekran startowy, nazwa w `app.json` i build przez EAS.
9. **Szybsze zakładanie.** Najwięcej czasu zajmuje start WP-CLI przy każdym poleceniu. Zgrupowanie konfiguracji
   w jednym `wp eval-file` i pakiety językowe wbudowane w obraz powinny skrócić zakładanie z około 105 s do około 30 s.
