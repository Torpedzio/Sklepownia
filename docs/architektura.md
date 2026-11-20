# Architektura

## Składniki

```
 Telefon / przeglądarka
 ┌────────────────────┐   JSON + JWT    ┌──────────────────┐   zadania   ┌─────────┐
 │ Aplikacja (Expo)   │ ──────────────▶ │ Backend (Django) │ ──────────▶ │  Redis  │
 │ iOS, Android, web  │ ◀────────────── │ API + admin      │             └────┬────┘
 └─────────┬──────────┘                 └────────┬─────────┘                  │
           │                                     │                            ▼
           │                               ┌─────▼──────┐              ┌──────────────┐
           │                               │ PostgreSQL │ ◀─────────── │ Worker Celery│
           │                               └────────────┘              └──────┬───────┘
           │                                                                  │ Docker API (socket)
           │ otwiera sklep i panel                                            ▼
           │                       Serwer sklepów (infra/shops)
           │                       ┌──────────────────────────────────────────────────────┐
           └─────────────────────▶ │ Traefik :8080 ──Host: <slug>.<domena>──▶ shop-<id>   │
                                   │             (WooCommerce, PrestaShop albo Magento)   │
                                   │                       MariaDB shops-db ◀─┤           │
                                   │            OpenSearch shops-search ◀─┘ (Magento)     │
                                   │  kopie zapasowe: restic w wolumenie shops-backups     │
                                   └──────────────────────────────────────────────────────┘
```

| Składnik | Rola | Gdzie |
|---|---|---|
| Aplikacja | Strony publiczne, konto, lista sklepów, formularz, postęp zakładania, porady | [mobile/](../mobile/) |
| Backend | REST API, uwierzytelnianie JWT, logika sklepów, panel admina Django | [backend/](../backend/) |
| PostgreSQL | Konta, sklepy, konfiguracja, zaszyfrowane hasła sklepów, postęp zakładania | `db` w [docker-compose.yml](../docker-compose.yml) |
| Redis | Kolejka zadań Celery | `redis` |
| Worker Celery | Wykonuje długie zadania: zakładanie i usuwanie sklepów, wysyłkę e-maili, odnowienia planów, sprawdzanie sklepów ([monitorowanie](#monitorowanie)) | `worker` |
| Celery beat | Zleca zadania według harmonogramu (`CELERY_BEAT_SCHEDULE`, czas polski): co 15 minut odnowienia planów, odczyt zamówień ze sklepów i potwierdzenia powiadomień push, co 5 minut płatności i faktury czekające na wynik oraz runda monitora, o 3:00 kopie zapasowe sklepów | `beat` |
| Tpay | Operator płatności: strona płatności kartą, zapisywanie i obciążanie karty, powiadomienia ([platnosci.md](platnosci.md)) | zewnętrzny |
| Mailpit | Lokalny serwer SMTP: przyjmuje całą pocztę i pokazuje ją w przeglądarce. Na produkcji zastępuje go dostawca poczty. | `mail` |
| Poczta sklepów | Przekaźnik, przez który sklepy wysyłają e-maile do klientów ([poczta sklepów](../infra/shops/README.md#poczta-sklepów)). Lokalnie drugi Mailpit, na produkcji przekaźnik do dostawcy poczty. | `shops-mail` |
| Traefik | Kieruje ruch do kontenera sklepu po nazwie hosta; adresy bez działającego sklepu do strony „Sklep chwilowo niedostępny” platformy | `shops-proxy` w [infra/shops/](../infra/shops/) |
| MariaDB | Jedna instancja, osobna baza i użytkownik dla każdego sklepu | `shops-db` |
| OpenSearch | Wyszukiwarka sklepów Magento, osobne indeksy dla każdego sklepu | `shops-search` |
| Kopie zapasowe | Repozytorium restic z kopiami baz i plików sklepów; kopie robi i przywraca jednorazowy kontener narzędzia uruchamiany przez workera ([kopie zapasowe](#kopie-zapasowe)) | wolumen `shops-backups`, obraz `shops/backup:0.19.1` |
| Kontener sklepu | Jeden na sklep: WordPress + WooCommerce + motyw, PrestaShop albo Magento ([platformy](#platformy-sklepów)) | `shop-<id>`, obraz `shops/wordpress:7.1`, `prestashop/prestashop:9.2.1-apache` albo `shops/magento:4.0.0` |

Backend i worker to ten sam kod. Tylko worker ma dostęp do socketu Dockera, bo tylko on zakłada kontenery.
Proces API nie dotyka Dockera (klient Dockera jest tworzony leniwie, dopiero przy pierwszym kroku).

## Przebieg zakładania sklepu

1. Aplikacja wysyła formularz: `POST /api/shops/`.
2. Backend w jednej transakcji ([services.create_shop](../backend/shops/services.py)):
   - blokuje wiersz użytkownika, sprawdza aktywny plan i jego limit sklepów (`Plan.max_shops`; sklepy testowe się nie liczą)
     oraz limit sklepów Magento (`Plan.max_magento_shops`),
   - tworzy `Shop` (status `pending`) i `ShopConfig` z wyborami z formularza,
   - tworzy `ProvisioningJob` z listą `ProvisioningStep` (po jednym na krok),
   - po zatwierdzeniu transakcji wrzuca zadanie `provision_shop` do kolejki.
3. Worker ([runner.run_job](../backend/shops/provisioning/runner.py)) zmienia status na `provisioning`
   i wykonuje kroki po kolei, zapisując stan każdego (`running`, `done`, `failed`).
4. Aplikacja co 1,5 s pobiera `GET /api/shops/{id}/` i rysuje postęp na paragonie.
5. Po ostatnim kroku sklep ma status `active`, a właściciel dostaje e-mail „Sklep … jest gotowy” ze szczegółami
   sklepu oraz loginem i hasłem do panelu WordPressa (`send_admin_access_email`). Przy błędzie: status `failed`, opis błędu przy kroku,
   a provisioner sprząta po nieudanej próbie (`cleanup`).
6. „Spróbuj ponownie” (`POST /api/shops/{id}/retry/`) tworzy nowe zadanie. Każdy krok jest idempotentny,
   więc kroki już wykonane po prostu przechodzą, a praca idzie dalej od miejsca błędu.

Kroki zakładania i ich techniczny opis: README platform w [infra/shops/](../infra/shops/README.md).

Usuwanie (`DELETE /api/shops/{id}/`) zmienia status na `deleted` od razu, a zadanie `teardown_shop`
usuwa kontener, wolumen, bazę i użytkownika bazy w tle. Adres (slug) usuniętego sklepu znów jest wolny.

## Ustawienia działającego sklepu

Źródłem prawdy jest WordPress: właściciel może zmieniać ustawienia także w wp-admin.
Backend trzyma ostatnio odczytany stan (`ShopSettings`), a pracę na sklepie wykonuje worker jako operacje (`ShopOperation`).

1. Ekran ustawień pobiera `GET /api/shops/{id}/settings/`. Jeśli ostatni odczyt jest starszy niż minuta,
   prosi o nowy (`settings/refresh/`): worker czyta wszystkie ustawienia ze sklepu jednym skryptem PHP.
2. Zapis sekcji (`PATCH`) wysyła tylko zmienione pola. Backend sprawdza je, odrzuca te bez zmian
   i tworzy operację `update_settings` z samymi zmianami ([services.update_settings](../backend/shops/services.py)).
3. Worker ([operations.run_operation](../backend/shops/provisioning/operations.py)) stosuje zmiany
   (`apply_settings`), zapisuje nowe wartości, aktualizuje `Shop.name` i `ShopConfig`, a na koniec znów czyta sklep.
4. Aplikacja co 1,5 s odpytuje ustawienia, dopóki `busy` jest prawdą, i zgłasza wynik paskiem powiadomień.

Na jednym sklepie trwa najwyżej jedna operacja. Operacja starsza niż 15 minut przestaje blokować kolejne
(np. gdy worker padł w jej trakcie). Po błędzie worker i tak czyta sklep, bo część zmian mogła już wejść.

Płatności online (Przelewy24, PayU w WooCommerce i PrestaShop) idą tą samą drogą, z dwiema różnicami:

- Klucze operatora nie zostają u nas. Czekają zaszyfrowane w operacji, worker wpisuje je do sklepu i je usuwa,
  a ustawienia i historia pamiętają tylko, że sklep ma klucze.
- Przy pierwszym włączeniu worker pobiera oficjalną wtyczkę lub moduł operatora z jego strony, w wersji i z sumą
  SHA-256 zapisanymi w kodzie, i instaluje w sklepie. Z operatorem łączy się potem sam sklep, przy płatnościach
  klientów; platforma nie rozmawia z API operatorów.

Regulamin i polityka prywatności też są częścią ustawień (sekcja `documents`), ale sklep ich nie podaje, tylko
dostaje:

- Platforma trzyma dane sprzedawcy i zasady zwrotów, a dokumenty pisze ze swoich wzorów i pozostałych ustawień
  ([documents.py](../backend/shops/documents.py)).
- Po włączeniu, a potem przy każdej zmianie, którą dokumenty opisują (np. nowa metoda płatności), worker w tej samej
  operacji publikuje je jako strony sklepu i podpina tam, gdzie platforma sklepu ich szuka (akceptacja regulaminu przy
  zamówieniu, stopka).
- Nowa wersja wzorów trafia do sklepów operacją `publish_documents`, zlecaną poleceniem `publish_shop_documents`.

## Sprzedaż w aplikacji

Zamówienia zostają w sklepie, a platforma trzyma ich kopię z ostatnich 90 dni (`ShopOrder`), bo tylko worker może
wejść do kontenera sklepu. Podsumowanie liczy się z kopii, więc otwiera się od razu.

1. Co 15 minut (`SHOP_ORDERS_SYNC_MINUTES`) beat zleca odczyt każdego działającego sklepu. Worker czyta tylko
   zamówienia zmienione od poprzedniego odczytu ([sales.sync](../backend/shops/sales.py)).
2. Ekran sprzedaży pobiera `GET /api/shops/{id}/sales/`. Gdy kopia ma ponad 2 minuty, backend zleca odczyt i zwraca
   `refreshing: true`, a aplikacja co 2,5 s pyta ponownie, pokazując do tego czasu poprzednie liczby.
3. Gdy odczyt się nie uda, kopia zostaje, a odpowiedź ma `error`. Następna próba jest przy kolejnym przebiegu
   harmonogramu albo po „Odśwież”.

Usunięcie sklepu usuwa też kopię jego zamówień.

## API sklepów

Codzienna obsługa sklepu w aplikacji (zamówienia, produkty, klienci) korzysta z REST API samej platformy sklepu,
a nie z poleceń w jego kontenerze. Dzięki temu backend wykonuje ją od razu, w zapytaniu aplikacji, bez kolejki i bez
dostępu do Dockera ([shops/remote/](../backend/shops/remote/)).

- Backend łączy się z sklepem pod jego publicznym adresem (`Shop.url`), tak jak przeglądarka klienta, więc działa
  tak samo, gdy sklepy stoją na osobnym serwerze.
- Każda platforma ma swój klucz w `ShopCredentials.api_key` (zaszyfrowany):

  | Platforma | API | Klucz |
  |---|---|---|
  | WooCommerce | `/wp-json/wc/v3/` | hasło aplikacji `platform` administratora (Basic Auth) |
  | PrestaShop | webservice przez `/webservice/dispatcher.php` (odpowiedzi w JSON, zapis w XML) | klucz webservice `Sklepownia` |
  | Magento | `/rest/all/V1/` | token integracji `Sklepownia` (Bearer) |

- Klucz powstaje w kroku zakładania „Połączenie z aplikacją”, a „Końcowe sprawdzenie” wymaga, żeby API go przyjęło.
  Przywrócenie kopii daje sklepowi nowy klucz, bo przywrócona baza ma klucz z dnia kopii. Sklepom sprzed tej funkcji
  albo takim, w których właściciel usunął klucz w panelu, nowy daje `connect_shop_api`
  ([obsluga.md](obsluga.md#połączenie-aplikacji-ze-sklepem)).
- Błędy są komunikatami dla właściciela (`ShopApiError`): sklep niedostępny (brak odpowiedzi albo strona „Sklep
  chwilowo niedostępny” z proxy), sklep bez klucza, klucz odrzucony, brak rzeczy w sklepie i błąd platformy z jej
  własnym opisem. Przekierowań klient nie wykonuje, żeby zapis nie zamienił się w odczyt ani klucz nie poszedł gdzie
  indziej.
- `FakeProvisioner` daje symulowane API (`shops.remote.fake.FakeApi`).

## Kopie zapasowe

Kopia to zrzut bazy sklepu i pliki z jego wolumenu, zapisane jako snapshot w repozytorium restic na serwerze sklepów
([szczegóły](../infra/shops/README.md#kopie-zapasowe)). Indeksem repozytorium jest `ShopBackup`: z niego aplikacja
pokazuje listę, a nocny przebieg decyduje, co usunąć ([backups.py](../backend/shops/backups.py)).

1. Co noc `beat` zleca `back_up_all_shops`: worker kopiuje po kolei sklepy działające i zawieszone (pomija te
   z trwającą operacją), a potem `maintain()`: uzgadnia indeks z repozytorium (usuwa wiersze kopii, których nie ma,
   przyjmuje kopie bez wiersza, usuwa kopie sklepów, których już nie ma) i usuwa kopie spoza okresu przechowywania.
2. Właściciel robi kopię (`create_backup`) albo przywraca jedną z listy (`restore_backup`). To operacje sklepu jak
   zmiana ustawień: jedna naraz, aplikacja odpytuje ich wynik.
3. Przywrócenie: kopia obecnego stanu, przywrócenie (kontener zatrzymany na około minutę), a potem sklep jest
   czytany od nowa: ustawienia, nazwa i region sklepu w platformie, dokumenty, zamówienia (kopia zamówień zaczyna się
   od zera, więc nie przychodzą powiadomienia o starych zamówieniach) i liczba produktów na liście startowej.
   Gdy przywrócenie się nie uda, sklep wraca do stanu sprzed próby tą samą drogą.
4. Usunięcie sklepu robi najpierw kopię „Stan sprzed usunięcia sklepu”, trzymaną 14 dni: obsługa może sklep przywrócić
   (`restore_shop`). Usunięcie konta usuwa kopie jego sklepów od razu (miejsce zwalnia się przy nocnym przebiegu).

## Monitorowanie

Monitor ([monitoring/](../backend/monitoring/)) pilnuje, czy klienci mogą wejść do sklepów i czy serwer sklepów ma
czym ich obsłużyć.

1. Kontener sklepu ma healthcheck: `curl` strony głównej z adresem sklepu wewnątrz kontenera, co minutę (przez
   pierwsze 5 minut po starcie co 3 s). Traefik kieruje ruch tylko do zdrowych kontenerów, więc gość startującego albo
   zepsutego sklepu widzi stronę „Sklep chwilowo niedostępny” zamiast błędu. Zakładanie, przywrócenie i naprawa
   czekają, aż kontener będzie zdrowy i Traefik zacznie kierować do niego ruch.
2. Co 5 minut `beat` zleca rundę. Worker sprawdza usługi serwera sklepów, a potem każdy działający sklep tak, jak
   wchodzi klient: przez Traefika, z nazwą hosta sklepu (zapytanie wychodzi z kontenera sklepu, bo worker nie jest
   w sieci sklepów). Porażka to brak odpowiedzi, błąd albo strona platformy zamiast sklepu (nagłówek
   `X-Shop-Unavailable`); sklep zamknięty w ustawieniach może odpowiadać `503`.
3. Zatrzymany kontener monitor uruchamia od razu. Sklep, który nie odpowiada dwa razy z rzędu, nie działa: monitor
   restartuje kontener (raz na awarię), czeka na healthcheck i sprawdza ponownie.
4. Gdy to nie pomaga, właściciel dostaje powiadomienie push i e-mail „Sklep nie działa, już to sprawdzamy”, aplikacja
   pokazuje przy sklepie „Nie odpowiada”, a obsługa dostaje e-mail z przyczyną na `ALERT_EMAILS`. Po pierwszym
   udanym sprawdzeniu oboje dostają „znowu działa”.
5. Obsługa słyszy też o usługach (Docker, proxy, baza, OpenSearch, poczta sklepów), małej ilości miejsca na dysku,
   prawie pełnym serwerze i kopiach zapasowych (nie udały się albo nie robiły się od ponad doby). Gdy nie działa
   Docker, proxy albo baza, runda nie ocenia sklepów: przyczyna jest jedna i obsługa już o niej wie.

Awarie są w panelu admina (Monitorowanie → Awarie). Runda kończy się pingiem `MONITOR_PING_URL`, jeśli jest
ustawiony: zewnętrzna usługa alarmuje, gdy pingi ustaną, czyli gdy padnie worker, beat albo cała platforma.

## Lista startowa

Ekran nowego sklepu pokazuje kroki do zrobienia przed sprzedażą
([checklist.py](../backend/shops/checklist.py)). Każdy odhacza się sam, z tego, co platforma już ma: ustawień
(płatności, wysyłka, regulamin), kopii zamówień (próbne zamówienie) i telefonów właściciela (powiadomienia). Liczby produktów
platforma nie zna, więc:

1. Otwarcie listy (`GET /api/shops/{id}/checklist/`) zleca liczenie produktów w sklepie, gdy krok z produktami jest
   otwarty, a ostatnie liczenie było ponad 2 minuty temu. Worker liczy własne i przykładowe produkty jednym zapytaniem
   w bazie sklepu i zapisuje je w `ShopChecklist`.
2. Do końca liczenia, odczytu zamówień albo zmiany ustawień odpowiedź ma `refreshing: true`, a aplikacja co 2,5 s
   pyta ponownie. Powrót do aplikacji z panelu sklepu pobiera listę od nowa.
3. Gdy oba kroki z produktami są zrobione, sklep nie jest już liczony. Ukryta lista nie zleca niczego.

## Powiadomienia push

Aplikacja na telefonie (build, nie Expo Go) po zgodzie właściciela pobiera token Expo i zgłasza go
(`POST /api/push/devices/`) przy starcie, po powrocie do aplikacji (najwyżej raz na godzinę) i po zmianie tokenu.

1. Zdarzenie (nowe zamówienie przy odczycie sprzedaży, koniec zakładania sklepu, nieudana opłata, koniec planu)
   woła `push.services.notify`. Po zatwierdzeniu transakcji worker wysyła powiadomienie na każdy telefon konta,
   o ile właściciel chce ten temat.
2. Expo Push przekazuje je do APNs (iOS) i FCM (Android). Odpowiedź (ticket) trafia do `PushTicket`.
3. Co 15 minut beat sprawdza potwierdzenia: telefon, który nie ma już aplikacji, jest usuwany.
4. Dotknięcie powiadomienia otwiera ekran z `data.url`, także gdy aplikacja była zamknięta.

O nowym zamówieniu powiadomienie przychodzi przy najbliższym odczycie sklepu, czyli z opóźnieniem do
`SHOP_ORDERS_SYNC_MINUTES`.

## Stany sklepu

| Stan | Znaczenie | Może przejść do |
|---|---|---|
| `pending` | Czeka w kolejce na workera | `provisioning`, `failed`, `deleted` |
| `provisioning` | Worker wykonuje kroki | `active`, `failed` |
| `active` | Sklep działa | `suspended`, `deleted` |
| `failed` | Zakładanie przerwane błędem | `pending` (ponowienie), `suspended`, `deleted` |
| `suspended` | Niedostępny w obecnym planie: kontener zatrzymany, dane zostają | `active`, `failed` (przywrócenie sklepu, którego zakładanie się nie skończyło), `deleted` |
| `deleted` | Usunięty (wiersz zostaje w bazie) | — (w ciągu 14 dni obsługa może go przywrócić z kopii poleceniem `restore_shop`, poza maszyną stanów) |

Dozwolone przejścia są w `Shop.ALLOWED_TRANSITIONS` ([models.py](../backend/shops/models.py)).
Niedozwolone przejście rzuca `InvalidTransition`; API zamienia je na `409 Conflict`
(np. usunięcie sklepu w trakcie zakładania). Stan `suspended` ustawia zmiana na plan z mniejszym limitem sklepów
([platnosci.md](platnosci.md#zmiana-planu)); zawieszone sklepy nie liczą się do limitu.

Pod adresem sklepu, którego kontener nie działa (zawieszony, jeszcze zakładany, restartujący się), gość widzi stronę
platformy z nazwą sklepu i szyldem „Nieczynne” albo „Wkrótce otwarcie” (`503`), a pod adresem bez sklepu
„Nie ma tu sklepu” (`404`) ([infra/shops/README.md](../infra/shops/README.md#adres-bez-działającego-sklepu)).

## Platformy sklepów

Klient wybiera w formularzu system, na którym działa sklep. Platformy opisuje [platforms/\_\_init\_\_.py](../backend/shops/platforms/__init__.py), a każda ma swój provisioner obok:
kroki zakładania widoczne na paragonie, sekcje ustawień, które aplikacja umie zmieniać, i nazwę panelu.
Motyw (`ShopTemplate`) należy do jednej platformy, a sklep (`Shop.platform`) ma ją na stałe.

| Platforma | Kontener | Panel | Ustawienia w aplikacji |
|---|---|---|---|
| WooCommerce | WordPress + WooCommerce + motyw, konfiguracja przez WP-CLI | `/wp-admin/`, login `admin` | wszystkie sekcje |
| PrestaShop 9 | oficjalny obraz, instalator wiersza poleceń, konfiguracja przez PHP w sklepie | losowy folder `admin…` (`Shop.admin_path`), login e-mailem | podstawowe, otwarcie sklepu, płatności, wygląd; wysyłka, podatki i region w panelu |
| Magento (Mage-OS 4) | własny obraz ze skompilowanym kodem, `bin/magento setup:install` i nasz moduł `Sklepownia_Provisioning`; wyszukiwarka w OpenSearch; min. 1,5 GB pamięci | losowy adres `admin_…` (`Shop.admin_path`), login `admin` | podstawowe, płatności, wysyłka, podatki, region; otwarcie sklepu, zakupy i wygląd w panelu |

Inne systemy, które rozważaliśmy, i ich ograniczenia: [ograniczenia-i-plan.md](ograniczenia-i-plan.md#inne-platformy-sklepów).

## Provisionery

Sposób zakładania sklepów wybiera zmienna `SHOP_PROVISIONER`:

| Wartość | Do czego |
|---|---|
| `shops.provisioning.fake.FakeProvisioner` | Symulacja bez infrastruktury, dla wszystkich platform: każdy krok czeka `FAKE_PROVISIONER_STEP_DELAY` sekund, opcjonalny błąd w kroku `FAKE_PROVISIONER_FAIL_AT_STEP`. Używany w testach. |
| `docker` | Prawdziwe sklepy na serwerze z [infra/shops/](../infra/shops/), każda platforma swoim provisionerem: `WooCommerceProvisioner`, `PrestaShopProvisioner` i `MagentoProvisioner`. Stara wartość `shops.provisioning.docker_provisioner.DockerProvisioner` znaczy to samo. |

`get_provisioner(shop.platform)` ([provisioning/\_\_init\_\_.py](../backend/shops/provisioning/__init__.py)) zwraca provisioner dla sklepu.
Wszystkie prawdziwe dziedziczą po `ContainerProvisioner` ([container.py](../backend/shops/provisioning/container.py)):
serwer, baza, kontener z regułą Traefika i limitem pamięci z planu, usuwanie, zawieszanie i wznawianie są wspólne.
Wszystkie provisionery dziedziczą po `BaseProvisioner`, który definiuje `cleanup`, `teardown` i `update_address`,
a dla działających sklepów `read_settings`, `apply_settings`, `reset_admin_password` i `remove_sample_products`.
`FakeProvisioner` trzyma ustawienia tylko w bazie platformy, a błąd można wywołać, podając w
`FAKE_PROVISIONER_FAIL_AT_STEP` nazwę metody (np. `apply_settings`).

## Adresy sklepów

Adres sklepu to `<scheme>://<slug>.<SHOPS_BASE_DOMAIN>[:port]`, liczony na bieżąco z ustawień
(`Shop.url`, `Shop.admin_url`). Ten sam adres jest zapisany w bazie sklepu i w regule Traefika kontenera,
więc po zmianie domeny trzeba przenieść istniejące sklepy poleceniem `update_shop_addresses`
([docs/obsluga.md](obsluga.md#zmiana-sieci-lub-adresu-ip)).

## Bezpieczeństwo

- Hasła sklepów (baza, administrator panelu, klucz API sklepu) są zaszyfrowane w bazie kluczem Fernet `FIELD_ENCRYPTION_KEY`
  (`EncryptedTextField`). Każde hasło jest zapisywane, zanim zostanie użyte, żeby ponowiona próba go nie zgubiła.
- Klucze płatności online sklepów są tylko w sklepie. Platforma trzyma je zaszyfrowane wyłącznie do końca operacji,
  która je zapisuje, i nigdy nie oddaje ich w API ani w panelu admina.
- Wtyczki instalowane w sklepach pobieramy tylko z przypiętych adresów i instalujemy tylko, gdy suma SHA-256 się zgadza.
- Login i hasło administratora sklepu nie wychodzą przez API. Trafiają tylko e-mailem na adres konta właściciela:
  po założeniu sklepu, po zmianie hasła i na prośbę (`send-admin-access`, najwyżej 5 razy na godzinę).
  Aplikacja pokazuje tylko adres panelu i adres, na który wysłano dane.
- Użytkownik widzi tylko sklepy, które ma albo obsługuje (`team.visible_shops`); obsługa może w nich tylko to, co
  wymienia `STAFF_ACTIONS` ([backend.md](backend.md#zespół)). Zakładanie i ponawianie wymaga potwierdzonego e-maila.
- Zaproszenie do zespołu przyjmie tylko konto z potwierdzonym adresem, na który je wysłano; link w e-mailu nie
  niesie tokenu, tylko prowadzi do logowania albo rejestracji.
- Komunikaty błędów kroków pokazywane użytkownikowi pochodzą tylko z `ProvisioningError`; inne wyjątki
  (mogące zawierać hasła lub nazwy hostów) zastępuje ogólny komunikat, a szczegóły trafiają do logów workera.
- Endpointy logowania, weryfikacji e-maila i formularza kontaktowego mają limity zapytań (throttling).
- Kopie zapasowe są szyfrowane hasłem `SHOPS_BACKUP_PASSWORD` (restic). Kontener narzędzia dostaje wolumen sklepu
  tylko do odczytu przy kopii; do zapisu tylko przy przywracaniu.
- Worker ma dostęp do socketu Dockera, czyli w praktyce uprawnienia roota na serwerze sklepów.
  Na produkcji trzeba to ograniczyć: [docs/ograniczenia-i-plan.md](ograniczenia-i-plan.md).
