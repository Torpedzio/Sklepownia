# Ograniczenia i plan

Stan na listopad 2026. Gdy coś z tej listy zostanie zrobione, usuń to stąd w tym samym commicie.

## Czego brakuje w funkcjach

- **Hasło w e-mailu:** dane logowania do panelu przychodzą zwykłym e-mailem. Bezpieczniejsze będzie logowanie
  jednym kliknięciem z aplikacji, bez przesyłania hasła.
- **Logowanie do panelu sklepu jednym kliknięciem.** Teraz aplikacja pokazuje login i hasło administratora.
  Pomysł: wtyczka „must-use” w WordPressie i jednorazowe linki logowania wydawane przez backend.
- **Atrybuty produktów według branży** (rozmiar, kolor, materiał), żeby filtry w sklepie miały z czego filtrować.
- **Ustawienia sklepu w aplikacji** obejmują podstawy, zakupy, płatności (przelew, przy odbiorze, Przelewy24 i PayU),
  wysyłkę w kraju sklepu, jedną stawkę VAT, region, motyw oraz regulamin i politykę prywatności. Brakuje logo
  i kolorów motywu oraz wysyłki za granicę.
- **Regulamin i polityka prywatności sklepu** ([backend.md](backend.md#regulamin-i-polityka-prywatności)):
  - wzory napisaliśmy sami według ustawy o prawach konsumenta, ustawy o świadczeniu usług drogą elektroniczną i RODO;
    **przed udostępnieniem właścicielom musi je przejrzeć prawnik** (po poprawkach: nowe `VERSION`
    i `publish_shop_documents`);
  - tylko po polsku i tylko dla sklepów sprzedających z Polski, dla sprzedaży towarów; nie opisują żywności, leków,
    usług, treści cyfrowych, subskrypcji ani sprzedaży firmom na innych zasadach;
  - przycisk odstąpienia od umowy w sklepie, którego wymaga dyrektywa (UE) 2023/2673 (art. 11a dyrektywy
    2011/83/UE, od 19 czerwca 2026), nie jest zrobiony; do sprawdzenia z prawnikiem, czy i jak go dodać;
  - polityka prywatności wskazuje platformę (`INVOICE_SELLER_*`) jako podmiot przetwarzający dane klientów sklepu,
    więc platforma potrzebuje umowy powierzenia z właścicielami (np. w regulaminie usługi). Zdanie o braku
    przekazywania danych poza EOG zakłada hosting i poczta w EOG;
  - opisujemy tylko płatności i dostawy ustawione w aplikacji; metody dodane w panelu sklepu (np. Tpay, paczkomaty)
    nie trafiają do regulaminu;
  - dokumentów nie czytamy ze sklepu: zmiany zrobione w panelu nadpisze następna publikacja, a wyłączenie dokumentów
    z aplikacji tylko zatrzymuje aktualizacje (strony zostają);
  - starszy regulamin nie jest archiwizowany: klient widzi tylko aktualną wersję, a e-mail z zamówieniem nie ma
    dokumentów w załączniku (trwały nośnik).
- **Płatności online w sklepach** (Przelewy24, PayU):
  - tylko WooCommerce i PrestaShop; w Magento właściciel podłączy w panelu tylko wbudowany PayPal, bo Magento 2.4
    nie instaluje modułów z panelu (Extension Directory w Mage-OS pokazuje tylko polecenia `composer`), a moduł
    operatora wymaga dostępu do serwera;
  - wtyczki i moduły instalujemy w wersji przypiętej w kodzie i nie aktualizujemy ich z aplikacji (aktualizacja to
    nowa wersja w `ONLINE_PAYMENTS`, sprawdzona na sklepie; właściciel może też zaktualizować wtyczkę w panelu);
  - konto Przelewy24 w PrestaShop i punkt PayU ustawiamy dla domyślnej waluty sklepu; inne waluty są w panelu;
  - przy pierwszej instalacji włączamy tylko główną płatność operatora: raty, „Kup teraz, zapłać później”
    i widżety kredytowe PayU są wyłączone, a osobne metody (np. BLIK jako osobny przycisk) włącza się w panelu;
  - aplikacja nie sprawdza kluczy u operatora: błędny klucz wyjdzie dopiero przy pierwszej płatności.
    Sprawdzenie kluczy w API operatora (sandbox) i płatność testowa z aplikacji to następny krok;
  - adres IP serwera dla panelu Przelewy24 trzeba wpisać ręcznie w panelu admina (`Server.public_ip`);
  - inni operatorzy (Tpay, Stripe, PayPal) tylko w panelu sklepu.
- **Płatności, dalsze etapy** ([platnosci.md](platnosci.md)):
  - zawieszanie sklepów (stan `suspended`), gdy plan wygaśnie lub zostanie anulowany, i usuwanie po okresie przechowania;
  - zmiana karty z aplikacji (nowa płatność z zapisaniem karty);
  - faktury korygujące (np. przy zwrocie) i własne połączenie z KSeF bez Fakturowni;
  - regulamin i polityka prywatności jako strony, do których prowadzą zgody przy płatności;
  - zniżki, okresy próbne, plany roczne, inne metody płatności (BLIK, przelew), wypłata salda przy rezygnacji.
- **Zamówienia w aplikacji** można oznaczyć jako opłacone, wysłane (z numerem przesyłki) albo anulować. Zwroty,
  edycja pozycji i adresów, faktury oraz anulowanie zamówienia z fakturą w Magento zostają w panelu sklepu.
  W PrestaShop przesyłka idzie przewoźnikiem wybranym w zamówieniu (aplikacja nie zmienia przewoźnika), a numer
  przesyłki nie trafia do e-maila o wysyłce (klient widzi go w szczegółach zamówienia na koncie); numer
  przesyłki w WooCommerce widać w notatce dla klienta, bo sklep nie ma pola na niego bez wtyczki. Lista zamówień
  i sumy pochodzą z kopii z 90 dni (starsze są tylko w panelu), sumy liczą tylko walutę sklepu, a nowe zamówienie
  pojawia się w aplikacji z opóźnieniem do 15 minut (od razu po „Odśwież”). Szczegóły zamówienia są czytane ze
  sklepu przy otwarciu, więc nie otworzą się, gdy sklep nie działa. Brakuje zestawień dłuższych niż 30 dni.
- **Powiadomienia push** o nowym zamówieniu przychodzą przy odczycie sklepu, więc do 15 minut po złożeniu, i na
  razie tylko do właściciela.
  Od razu dawałby je webhook sklepu (WooCommerce `order.created`) wołający platformę. Aplikacja nie ma jeszcze
  projektu EAS ani kluczy FCM i APNs, więc powiadomienia działają dopiero po ich dodaniu i w buildzie, nie w Expo Go.
  Brakuje powiadomień o niskim stanie magazynu.
- **Lista startowa** odhacza tylko to, co platforma widzi: ustawień robionych w panelu sklepu (np. wysyłki
  w PrestaShop, logo, danych firmy) nie sprawdza i ich nie pokazuje. Ustawienia zmienione w panelu odhaczają się po
  otwarciu ustawień w aplikacji, które czyta je ze sklepu. Krok powiadomień wymaga buildu aplikacji (patrz niżej).
  Ukrytej listy nie da się jeszcze przywrócić z aplikacji (API to umie: `PATCH … {hidden: false}`).
- **Testy na urządzeniu:** testy aplikacji działają w Jest; zachowania zależne od urządzenia (przewijanie,
  klawiatura, animacje) sprawdza się ręcznie w Expo Go.
- **Pamięć podręczna danych** w aplikacji jest tylko w pamięci: po ponownym uruchomieniu aplikacji albo odświeżeniu
  strony ekrany zaczynają od ładowania, a bez sieci aplikacja nie pokaże ostatnich danych.
- **Strona w przeglądarce** ([aplikacja-mobilna.md](aplikacja-mobilna.md#strona-w-przeglądarce)):
  - jeden obrazek podglądu linku dla wszystkich stron; dane strukturalne mówią tylko, kto prowadzi serwis (bez cen
    planów i pytań);
  - serwer zgaduje szerokość okna po urządzeniu, więc na komputerze z wąskim oknem układ zmienia się na wąski
    zaraz po załadowaniu;
  - ekrany za logowaniem mają w karcie przeglądarki tylko nazwę serwisu;
  - plany w stronie z serwera przeglądarka trzyma do przeładowania strony (dane `loader` są zapamiętywane na sesję).
- **Monitorowanie** ([architektura.md](architektura.md#monitorowanie)): monitor nie ma historii dostępności ani
  strony stanu dla właścicieli (tylko awarie w panelu admina), nie alarmuje o wolnych sklepach (czas odpowiedzi
  zapisuje bez progu) ani o błędach zakładania sklepów. Sprawdza sklep od środka serwera sklepów, więc nie widzi
  problemów z DNS, HTTPS i certyfikatem; to wymaga sprawdzania z zewnątrz. Kontenery sprzed healthchecka trzeba
  raz odtworzyć (`update_shop_containers`).
- **Zdjęcia w przykładowych produktach.** Produkty przykładowe nie mają zdjęć, więc nowy sklep pokazuje szare zaślepki.
- **Porady w innych językach.** Instrukcja logowania i porady podają polskie nazwy z paneli WordPressa,
  PrestaShop i Magento, także dla sklepów założonych w innym języku. Polski pakiet Magento nie tłumaczy kilku
  nazw (np. „Delivery Methods”), więc porady podają je po angielsku, tak jak w panelu.
- **Porady PrestaShop i Magento otwierają stronę startową panelu.** Adresy stron w ich panelach zawierają token sesji
  albo tajny klucz, więc przycisk przy poradzie nie przeniesie od razu na właściwą stronę.

## Plan: obsługa sklepu w aplikacji i zespół

Cel: najważniejsze czynności prowadzenia sklepu są w aplikacji, a panel sklepu zostaje opcją awaryjną; do obsługi
sklepu właściciel dodaje inne osoby. Ustalenia: dwie stałe role (właściciel, obsługa) bez wybierania uprawnień;
liczba osób w zespole według planu (start do 5, standard do 20, business bez limitu); wszystko od razu na trzech
platformach; dostęp obsługi do panelu sklepu później. Podstawą jest API sklepów
([architektura.md](architektura.md#api-sklepów)). Kolejne kroki:

Role i zaproszenia już są ([backend.md](backend.md#zespół)): obsługa ogląda sklep, sprzedaż i zamówienia, resztę
robi właściciel; nowe czynności (obsługa zamówień, produkty, stany, klienci, rabaty) trafią do `STAFF_ACTIONS`. Zaprasza się
e-mailem z linkiem do aplikacji, a zaproszenie czeka na liście sklepów osoby zaproszonej. Przy rejestracji wybiera
się „Zakładam sklep” albo „Dołączam do zespołu” (bez cennika, z ekranem czekania na zaproszenie). Właściciel
prowadzi zespół na ekranie sklepu, a obsługa widzi tylko to, co może zrobić. Historia działań pokazuje właścicielowi,
kto co zmienił; nowe czynności dopisują do niej swoje wpisy. Zamówienia już są: lista z filtrami, szczegóły
czytane ze sklepu, zmiana statusu z numerem przesyłki i notatki zespołu ([backend.md](backend.md#zamówienia)).

1. **Produkty:** lista, dodawanie i edycja (cena, promocja, opis, kategoria, SKU, stan), zdjęcia z aparatu,
   ukrywanie i usuwanie; warianty na razie w panelu. Do tego szybka zmiana stanów magazynowych.
2. **Powiadomienia według osoby** (nowe zamówienia także dla obsługi, awarie) i przypadki brzegowe zespołu
   (usunięcie konta członka, sklepu z zespołem).
3. **Kategorie, klienci (z wnioskami RODO) i kody rabatowe.**
4. **Co zostaje w panelu:** lista z linkami „Otwórz w panelu” i poradami.

Klucz API sklepu może usunąć właściciel w panelu; aplikacja zgłasza wtedy odrzucony klucz, a naprawia to dopiero
`connect_shop_api`. Do rozważenia: samoczynne odnowienie klucza przez worker.

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
   Strona platformy potrzebuje serwera Node (renderuje strony): `npx expo export --platform web` i adapter
   `expo-server` albo EAS Hosting ([aplikacja-mobilna.md](aplikacja-mobilna.md#strona-w-przeglądarce)), z `SITE_URL`
   ustawionym na jej adres. Potem mapa strony w Google Search Console.
2. **Bezpieczny dostęp do Dockera.** Worker ma dziś surowy socket Dockera, czyli uprawnienia roota.
   Trzeba go odseparować, np. przez proxy socketu ograniczające dozwolone operacje
   albo osobny agent na serwerze sklepów z własnym API.
3. **Serwer aplikacji.** Gunicorn lub uvicorn zamiast `runserver`, `DJANGO_DEBUG=0`, konkretne `DJANGO_ALLOWED_HOSTS`
   (z hostem z `SHOPS_FALLBACK_URL` serwera sklepów) i `CORS_ALLOWED_ORIGINS`, pliki statyczne, kopie zapasowe PostgreSQL.
4. **Kopie zapasowe poza serwerem.** Kopie sklepów są dziś w repozytorium restic na serwerze sklepów
   ([infra/shops/README.md](../infra/shops/README.md#kopie-zapasowe)), więc nie przetrwają utraty serwera. Trzeba je
   kopiować na zewnątrz (`restic copy` albo drugie repozytorium w S3 lub B2, z osobnym hasłem), regularnie sprawdzać
   repozytorium (`restic check`, co jakiś czas z `--read-data-subset`). Hasło repozytorium musi być w sejfie poza
   serwerem.
5. **Poczta:** dostawca SMTP dla platformy (zmienne `EMAIL_*`, zamiast Mailpit) z rekordami SPF i DKIM domeny.
   Dla sklepów przekaźnik na serwerze sklepów w miejsce `shops-mail` (np. Postfix), który trzyma dane logowania
   do dostawcy i przepuszcza tylko nadawców z `SHOPS_MAIL_DOMAIN`, z limitem wiadomości na sklep. Domena
   `SHOPS_MAIL_DOMAIN` potrzebuje SPF i DKIM, a poczta przychodząca na `<slug>@` najlepiej przekierowana
   do właściciela, gdyby ktoś odpisał na adres nadawcy zamiast na Reply-To.
6. **Monitorowanie platformy z zewnątrz:** `MONITOR_PING_URL` z usługą, która alarmuje, gdy rundy monitora ustaną
   (padł worker, beat albo serwer), sprawdzanie API i strony platformy oraz kilku sklepów spoza serwera (DNS, HTTPS,
   certyfikaty), `ALERT_EMAILS` z adresami dyżurnych i zbieranie błędów aplikacji (np. Sentry).
7. **Wiele serwerów sklepów.** Model `Server` i krok przydziału serwera są gotowe, ale provisionery
   rozmawiają tylko z lokalnym Dockerem.
8. **Aplikacja w sklepach z aplikacjami:** ikony, ekran startowy, nazwa w `app.json` i build przez EAS.
9. **Szybsze zakładanie.** Najwięcej czasu zajmuje start WP-CLI przy każdym poleceniu. Zgrupowanie konfiguracji
   w jednym `wp eval-file` i pakiety językowe wbudowane w obraz powinny skrócić zakładanie z około 105 s do około 30 s.
