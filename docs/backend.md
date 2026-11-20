# Backend

Django 5.2 + Django REST Framework, Celery z Redisem, PostgreSQL. Kod w [backend/](../backend/).

## Struktura

```
backend/
├── config/            ustawienia, główne URL-e, konfiguracja Celery
├── accounts/          użytkownicy, rejestracja, logowanie JWT, potwierdzanie e-maila
├── shops/             sklepy: modele, API, zakładanie (provisioning), polecenia
│   ├── platforms/     __init__.py (platformy: kroki, sekcje ustawień, panel), woocommerce.py, prestashop.py, magento.py,
│   │                  files/ (pliki instalowane w sklepach: wtyczki poczty i stopki z regulaminem WordPressa,
│   │                  moduł poczty PrestaShop)
│   ├── provisioning/  base.py (kroki), container.py (wspólne dla kontenerów), runner.py (zakładanie),
│   │                  operations.py (operacje na działającym sklepie), packages.py (wtyczki pobierane od producentów),
│   │                  fake.py (symulacja)
│   ├── remote/        REST API sklepów: wspólny klient i błędy (__init__.py), woocommerce.py, prestashop.py,
│   │                  magento.py, fake.py (symulacja)
│   ├── management/    polecenia update_shop_addresses, configure_shop_mail, publish_shop_documents, backup_shops,
│   │                  restore_shop, update_shop_containers i connect_shop_api
│   ├── categories.py  nazwy kategorii według branży
│   ├── emails.py      e-mail z danymi sklepu i logowaniem (szablony w templates/shops/email/)
│   ├── orders.py      zamówienie odczytane ze sklepu (Order), wspólne dla platform
│   ├── sales.py       kopia zamówień ze sklepów i podsumowanie sprzedaży dla aplikacji
│   ├── checklist.py   lista startowa nowego sklepu: kroki odhaczane same i liczenie produktów
│   ├── backups.py     kopie zapasowe: kopia, przywrócenie, nocny przebieg, przechowywanie, lista dla aplikacji
│   ├── unavailable.py strona pod adresem sklepu, którego kontener nie działa (szablon templates/shops/unavailable.html)
│   ├── documents.py   regulamin i polityka prywatności sklepu ze wzorów (templates/shops/documents/), wersja wzorów
│   ├── choices.py     branże, języki, waluty, kraje, zakres liczby kategorii
│   ├── fields.py      EncryptedTextField (szyfrowanie Fernet)
│   ├── services.py    create_shop, retry_shop, delete_shop, get_settings, update_settings, start_operation
│   ├── shop_settings.py  sekcje ustawień sklepu: pola, etykiety, walidacja, wartości domyślne
│   └── slugs.py       zasady adresów sklepów i lista zarezerwowanych
├── billing/           plany, dane do faktury, płatności, odnowienia, faktury (invoices.py, invoicing/), operatorzy płatności (gateways/)
├── push/              powiadomienia push: telefony, tematy, wysyłka (senders/: Expo, log, pamięć), teksty (messages.py)
├── monitoring/        monitor sklepów i serwera sklepów: runda i naprawy (checks.py), awarie i kto o nich słyszy
│                      (alerts.py), teksty (texts.py, templates/monitoring/), polecenie check_shops
├── support/           formularz kontaktowy
├── handbook/          dokumentacja projektu (pliki Markdown) jako strony pod /docs/
└── conftest.py        wspólne fixtures testów
```

Zasada podziału: widoki (`views.py`) tylko sprawdzają dane i wołają funkcje z `services.py`.
Logika biznesowa, transakcje i kolejkowanie zadań są w serwisach.

## Aplikacja `accounts`

- **`User`** loguje się e-mailem (bez nazwy użytkownika). Pole `is_email_verified` mówi, czy e-mail jest potwierdzony.
- **`EmailVerificationCode`** to jeden aktywny kod na użytkownika, przechowywany jako hash.
  - Kod jest ważny 15 minut (`EMAIL_VERIFICATION_CODE_TTL`) i ma limit 5 prób (`EMAIL_VERIFICATION_MAX_ATTEMPTS`).
  - Nowy kod można wysłać najwcześniej po 60 s (`EMAIL_VERIFICATION_RESEND_COOLDOWN`).
- **Logowanie:** JWT (simplejwt). Token dostępu jest ważny 30 minut, token odświeżania 30 dni.
  - Przy każdym odświeżeniu backend wydaje nowy token odświeżania, a stary trafia na czarną listę (`token_blacklist`).
  - Wylogowanie dopisuje token odświeżania do czarnej listy.
- **Potwierdzony e-mail** jest wymagany do zakładania i ponawiania sklepów (`IsEmailVerified`).
- **`GET /api/auth/me/`** zwraca dane konta razem z `shop_limit`, żeby aplikacja mogła zablokować przycisk nowego
  sklepu, i `magento_shop_limit`, który ekran konta pokazuje obok sklepów Magento.
- **Usunięcie konta** (`delete_account`) to anonimizacja, nie skasowanie wiersza, bo płatności (`Payment.user`, `PROTECT`)
  trzeba przechowywać dla przepisów podatkowych.
  - E-mail zmienia się na `deleted-{id}@deleted.invalid`, a imię, nazwisko, zdjęcie i hasło znikają.
    Konto dostaje `is_active=False` i `deleted_at`, a jego tokeny trafiają na czarną listę.
  - Sklepy są usuwane (`delete_all_shops`). `teardown_shop` po sprzątnięciu kontenera kasuje też wiersz sklepu,
    gdy właściciel nie ma już konta.
  - Plan kończy się od razu jako `canceled` bez karty (`close_account`), czekające płatności są nieudane,
    a dane do faktury (`BillingProfile`) znikają. Płatność opłacona po usunięciu konta trafia do logu błędów jako do zwrotu.
  - Wiadomości z formularza kontaktowego zostają, bo to korespondencja z obsługą.

## Aplikacja `shops`

### Modele

| Model | Opis |
|---|---|
| `Server` | Serwer, na którym działają kontenery sklepów, z limitem `max_shops`. `public_ip` to adres, z którego sklepy łączą się z operatorami płatności (aplikacja pokazuje go przy Przelewy24). Migracja tworzy serwer `local`. |
| `ShopTemplate` | Motyw do wyboru w formularzu, dla jednej platformy (`platform`). `theme` to nazwa motywu w systemie sklepu. Migracje dodają Storefront, Astrę i Kadence (WooCommerce) oraz Hummingbird i Classic (PrestaShop). |
| `Shop` | Sklep: właściciel, nazwa, `slug` (część adresu), platforma, status z maszyną stanów, serwer. `url` i `admin_url` są liczone z ustawień; folder panelu PrestaShop jest w `admin_path`. |
| `ShopConfig` | Wybory z formularza: branża, motyw, liczba kategorii, język, waluta, kraj, e-mail, produkty przykładowe. Zmiany z ustawień (opis, e-mail, język, waluta, kraj, motyw) są tu dopisywane. |
| `ShopCredentials` | Login administratora (`admin_login`: nazwa użytkownika w WordPressie, e-mail w PrestaShop) i hasła: bazy, administratora, API WordPressa. Hasła zaszyfrowane. |
| `ProvisioningJob` | Jedna próba założenia sklepu (status, błąd, czasy). Ponowienie tworzy nowe zadanie. |
| `ProvisioningStep` | Krok zadania: klucz, etykieta dla użytkownika, status, błąd, czasy. |
| `ShopSettings` | Ostatnio odczytane albo zapisane ustawienia sklepu (`values`, JSON w sekcjach) i czas odczytu ze sklepu. |
| `ShopOperation` | Praca na działającym sklepie: zmiana ustawień, odczyt ustawień, nowe hasło, usunięcie produktów przykładowych, kopia zapasowa i jej przywrócenie (`backup`: kopia zrobiona albo przywracana). Zmienione pola, wynik, błąd, kto zlecił. Służy też jako historia zmian. `secrets` (zaszyfrowane) trzyma klucze płatności online tylko do końca operacji. |
| `ShopBackup` | Kopia zapasowa sklepu, indeks repozytorium restic: rodzaj (`nightly`, `manual`, `before_restore`, `before_delete`), stan (gotowa albo błąd z opisem dla admina), `snapshot_id` (unikalny), rozmiar, czas. Zostaje po usunięciu sklepu, dopóki trzyma ją okres przechowywania. |
| `ShopOrder` | Kopia zamówienia ze sklepu z ostatnich 90 dni: numer, status sprowadzony do pięciu wspólnych, suma, waluta, liczba sztuk, klient jako „Anna N.”, czas złożenia i ostatniej zmiany. Unikalne po `(shop, external_id)`. |
| `ShopChecklist` | Lista startowa sklepu: `products` i `sample_products` (policzone w sklepie, `null` przed pierwszym liczeniem), `counted_at` (udane liczenie), `attempted_at` (ostatnia próba), `requested_at` (zlecone przy otwarciu listy), `hidden_at` (właściciel ukrył listę). Kroki: `ShopChecklist.Step`. |
| `SalesSync` | Stan odczytu zamówień sklepu: `cursor` (ostatnia zmiana, od której czytać), `synced_at` (udany odczyt), `attempted_at` (ostatnia próba), `requested_at` (zlecony z aplikacji), `error`. |

`slug` musi być unikalny tylko wśród sklepów, które nie są usunięte (ograniczenie `unique_slug_for_live_shops`).
Zasady adresu: 3–30 znaków, małe litery, cyfry i pojedyncze myślniki, nie na początku ani na końcu,
bez adresów zarezerwowanych dla platformy ([slugs.py](../backend/shops/slugs.py)).

### Zakładanie sklepu

Przebieg i stany: [architektura.md](architektura.md#przebieg-zakładania-sklepu).

- Kroki każdej platformy to lista par `(klucz, etykieta)` w [platforms/\_\_init\_\_.py](../backend/shops/platforms/__init__.py).
  Etykiety widzi właściciel sklepu na paragonie, więc mówią, co sklep dostaje, a nie jak to jest robione.
- Provisioner implementuje metodę `step_<klucz>(shop)` dla każdego kroku. **Każdy krok musi być idempotentny**:
  ponowienie uruchamia wszystkie kroki od nowa.
- `runner.run_job` wykonuje kroki i zapisuje ich stan. Użytkownik widzi treść tylko wyjątków `ProvisioningError`.
  Pozostałe wyjątki zastępuje ogólny komunikat, a pełny opis ląduje w logach workera.
- `ContainerProvisioner` ([container.py](../backend/shops/provisioning/container.py)) tworzy kontener `shop-<id>`,
  wolumen `shop-<id>` i bazę `shop_<id>`. Kontener jest odtwarzany, gdy zmieni się jego środowisko, adres, limit
  pamięci albo obraz. Pocztę sklepu (`configure_mail`, [poczta sklepów](../infra/shops/README.md#poczta-sklepów))
  każda platforma ustawia w kroku konfiguracji sklepu. Na nim stoją:
  - `WooCommerceProvisioner` ([woocommerce.py](../backend/shops/platforms/woocommerce.py)): WordPressa konfiguruje
    przez WP-CLI w kontenerze. Ustawienia zależne od motywu (pasek boczny) są w `THEME_NAVIGATION`.
    Szczegóły i pułapki: [infra/shops/woocommerce/README.md](../infra/shops/woocommerce/README.md).
  - `PrestaShopProvisioner` ([prestashop.py](../backend/shops/platforms/prestashop.py)): instaluje sklep
    instalatorem `install/index_cli.php`, a resztę robi skryptami PHP uruchamianymi w sklepie (`_php`, dane w `$d` jak w WordPressie).
    Szczegóły i pułapki: [infra/shops/prestashop/README.md](../infra/shops/prestashop/README.md).
  - `MagentoProvisioner` ([magento.py](../backend/shops/platforms/magento.py)): instaluje sklep `bin/magento setup:install`,
    a resztę robi poleceniem `sklepownia:run <akcja>` z naszego modułu w obrazie (dane jako base64 w zmiennej
    środowiskowej `SKLEPOWNIA_DATA`, wynik JSON po znaczniku). Kod Magento jest w obrazie, w wolumenie tylko dane sklepu
    (`VOLUME_PATH`), a pamięci dostaje co najmniej `SHOPS_MAGENTO_MEMORY` (`memory()`).
    Szczegóły i pułapki: [infra/shops/magento/README.md](../infra/shops/magento/README.md).

Jak dodać nowy krok:

1. Dopisz `("klucz", "Etykieta dla użytkownika")` do kroków platformy w `platforms.py` we właściwym miejscu.
2. Dodaj `step_klucz(self, shop)` w provisionerze tej platformy. Krok ma działać także przy ponownym uruchomieniu.
3. Opisz krok w tabeli kroków w README platformy w [infra/shops/](../infra/shops/README.md).
4. Jeśli etykieta ma się pokazać na paragonie na stronie głównej, dopisz ją też do `SetupSteps`
   w [mobile/src/constants/content.ts](../mobile/src/constants/content.ts).

### Ustawienia sklepu

Przebieg: [architektura.md](architektura.md#ustawienia-działającego-sklepu). Sekcje i pola: [api.md](api.md#ustawienia-i-operacje-na-działającym-sklepie).

- Schemat ustawień to serializery sekcji w [shop_settings.py](../backend/shops/shop_settings.py). Etykiety pól
  trafiają do historii zmian, więc piszemy je językiem właściciela sklepu.
- `WooCommerceProvisioner.read_settings` czyta wszystko jednym `wp eval` (`READ_SETTINGS_PHP`) i zamienia na sekcje.
  Zapis idzie sekcjami: opcje WordPressa, płatności (`woocommerce_bacs_*`, `woocommerce_cod_settings`),
  stawka VAT i strefa wysyłki przez klasy WooCommerce. Dane do PHP trafiają jako base64 w `$d`, więc nic ich nie przerwie.
- Platforma zapamiętuje w opcjach WordPressa identyfikatory swojej strefy wysyłki (`sklepownia_shipping_zone_id`)
  i stawki VAT (`sklepownia_tax_rate_id`). Inne strefy i stawki dodane w wp-admin zostają nietknięte.
- Zmiana języka i motywu korzysta z kodu kroków zakładania; pasek boczny jest przebudowywany raz, po zmianie języka,
  motywu albo opinii (filtr ocen istnieje tylko przy włączonych opiniach).
- Produkty przykładowe mają metadane `_sklepownia_sample`. Starsze sklepy rozpoznaje się po nazwie „Przykładowy produkt N”.

Płatności online (Przelewy24, PayU) na WooCommerce i PrestaShop:

- Operatorzy platformy są w `payment_operators` w `platforms.py`, a ich pola w `PaymentsSection` i `OPERATORS`
  w [shop_settings.py](../backend/shops/shop_settings.py).
- Klucze (`SecretField`) nie trafiają do `ShopSettings` ani do `changes` operacji. `services.update_settings` oddziela
  je (`split_secrets`) i zapisuje zaszyfrowane w `ShopOperation.secrets`. Worker wstawia je z powrotem tuż przed
  `apply_settings` (`reveal`), a w zapisanych ustawieniach zostawia tylko `{operator}_keys_saved` (`conceal`).
  `_finish` czyści `secrets` po każdej operacji. `start_operation` czyści też klucze operacji starszych niż
  `OPERATION_TIMEOUT`, które nigdy się nie skończyły.
- Wtyczki operatorów pobiera worker z adresów producentów w wersji przypiętej w kodzie (`ONLINE_PAYMENTS`
  w `woocommerce.py` i `prestashop.py`). Plik musi mieć zapisaną sumę SHA-256, inaczej go nie instalujemy
  ([packages.py](../backend/shops/provisioning/packages.py)). Pobrane pliki leżą w `SHOPS_PACKAGE_CACHE`,
  a do kontenera trafiają przez `ContainerProvisioner._upload` (archiwum tar, bez sieci w sklepie).
  Nowa wersja wtyczki to nowy adres, wersja i suma, sprawdzone na prawdziwym sklepie.
- WooCommerce: wtyczkę instaluje `wp plugin install` z pliku. Konto Przelewy24 zapisujemy przed włączeniem wtyczki,
  a PayU po nim, bo PayU wpisuje swoje domyślne ustawienia przy włączeniu. Przy pierwszej instalacji włączamy tylko
  główną bramkę operatora (`p24-online-payments`, `payustandard`), a raty i widżety kredytowe PayU są wyłączone.
- PrestaShop: moduł rozpakowujemy do `modules/` i instalujemy przez `Module::install()` w jądrze panelu
  (`kernel=True`). Konto Przelewy24 jest w tabelach modułu dla domyślnej waluty sklepu, PayU w konfiguracji
  (`PAYU_MC_*` dla waluty).
- Wyłączenie operatora wyłącza tylko płatność, wtyczka z ustawieniami zostaje. Operator, którego pól nie ma w zmianie,
  jest nietknięty, więc nie nadpisujemy tego, co właściciel ustawił w panelu.

Nowe ustawienie: pole w serializerze sekcji, wartość domyślna w `default_settings`, odczyt w `read_settings`,
zapis w `apply_settings`, pole w `ShopSettingsValues` w aplikacji i kontrolka na ekranie ustawień.

Każda platforma ma listę sekcji, które aplikacja umie zmieniać (`settings_sections` w `platforms.py`).
API zwraca ją jako `sections`, aplikacja pokazuje tylko te sekcje, a zmiana innej sekcji kończy się `400`.
`read_settings` zwraca tylko sekcje platformy; pozostałe zostają z wartościami domyślnymi.
PrestaShop: produkty przykładowe są zapamiętane po identyfikatorach w konfiguracji sklepu (`SKLEPOWNIA_SAMPLE_PRODUCTS`).

Nowa platforma: wpis w `Platform` i `PLATFORMS` (kroki, sekcje, nazwa panelu), provisioner (zwykle na `ContainerProvisioner`)
w `DOCKER_PROVISIONERS`, motywy migracją danych, metoda `step_<klucz>` symulacji tam, gdzie powstają dane logowania.

Istniejące sklepy mają kroki zapisane w bazie. Nowy krok pojawi się u nich dopiero przy ponowieniu.
Zmianę etykiet istniejących kroków trzeba przenieść migracją danych (przykład: `0005_plain_step_labels`).

### Regulamin i polityka prywatności

Pola i zasady: [api.md](api.md#ustawienia-i-operacje-na-działającym-sklepie).

- Wzory to szablony Django w [templates/shops/documents/](../backend/shops/templates/shops/documents/):
  `terms.html` (regulamin z wzorem formularza odstąpienia) i `privacy.html` (informacje z art. 13 RODO). Używają
  tylko `h2`, `p`, `ol`, `ul`, `li`, `strong`, żeby wyglądały dobrze w każdym motywie każdej platformy.
  [documents.py](../backend/shops/documents.py) wypełnia je ustawieniami (`render`) i zamienia na bloki tekstu dla
  podglądu w aplikacji (`blocks`). Numery paragrafów regulaminu liczy `_context`, bo paragraf o opiniach jest tylko
  przy włączonych opiniach.
- Wzory są wersją do sprawdzenia przez prawnika. Po każdej zmianie treści podnieś `VERSION` w `documents.py`
  i uruchom `publish_shop_documents`, żeby sklepy z dokumentami z aplikacji dostały nowy tekst.
- Publikuje worker: `_update_settings` w [operations.py](../backend/shops/provisioning/operations.py) po zapisaniu
  zmian w sklepie woła `publish_documents`, gdy dokumenty są włączone, a zmiana dotyczy sekcji opisanych
  w dokumentach (`documents.INPUT_SECTIONS`). Adresy stron i wersja wzorów trafiają do sekcji `documents`
  zapisanych ustawień. Sekcja nie jest czytana ze sklepu, więc odczyt ustawień jej nie nadpisuje.
- `publish_documents(shop, documents)` w provisionerze platformy zwraca `{key: adres strony}`:
  - WooCommerce: strony WordPressa wskazane w `woocommerce_terms_page_id` (regulamin, pole akceptacji przy
    zamówieniu) i `wp_page_for_privacy_policy` (polityka prywatności WordPressa i WooCommerce). Istniejąca strona
    jest nadpisywana, brakująca tworzona. Linki w stopce każdego motywu dodaje wtyczka mu-plugin
    `sklepownia-documents.php` (`files/woocommerce/`), wgrywana przy każdej publikacji.
  - PrestaShop: strony CMS. Regulamin to strona z `PS_CONDITIONS_CMS_ID` (pole akceptacji przy zamówieniu,
    `PS_CONDITIONS`), polityka prywatności to strona z `SKLEPOWNIA_PRIVACY_CMS_ID`, dopisana do bloku linków
    `ps_linklist` z regulaminem (stopka).
  - Magento: akcja `documents` modułu `Sklepownia_Provisioning`. Strony CMS `regulamin` i
    `privacy-policy-cookie-restriction-mode` (link w stopce Luma), zgoda „Akceptuję regulamin sklepu” przy
    zamówieniu (`checkout/options/enable_agreements`) i link „Regulamin” w stopce z layoutu modułu
    (`sklepownia/documents/terms_link`). Kontener ze starszego obrazu jest najpierw odtwarzany
    (`step_start_container`).
- Podgląd (`POST shops/{id}/documents/preview/`) liczy dokumenty w procesie WWW, bez workera i bez sklepu.

### Sprzedaż

Przebieg: [architektura.md](architektura.md#sprzedaż-w-aplikacji). Pola odpowiedzi: [api.md](api.md#sprzedaż).

- Backend WWW nie ma dostępu do kontenerów sklepów, więc zamówienia czyta worker (`sales.sync`) i zapisuje kopię
  w `ShopOrder`. API liczy podsumowanie z kopii (`sales.overview`).
- Odczyt jest przyrostowy: od `cursor` minus 10 minut (zmiany zapisane z opóźnieniem), partiami po 500, najwyżej
  10 partii naraz. Pierwszy odczyt bierze 90 dni. Starsze zamówienia są usuwane z kopii.
- `select_for_update(skip_locked=True)` na `SalesSync`: drugi odczyt tego samego sklepu (z harmonogramu i z aplikacji)
  pomija sklep zamiast czekać.
- Otwarcie podsumowania zleca odczyt, gdy ostatnia próba była ponad 2 minuty temu, przycisk „Odśwież” po 30 sekundach.
  Nieudana próba też się liczy, więc zepsuty sklep nie jest odpytywany przy każdym wejściu.
- `read_orders(shop, since, limit)` w provisionerze platformy zwraca zamówienia zmienione od `since`, od najstarszej
  zmiany. WooCommerce: `wc_get_orders` przez `wp eval` (działa przy HPOS i przy wpisach). PrestaShop: SQL przez `Db`
  w skrypcie PHP, czasy przeliczone ze strefy sklepu. Magento: SQL na `sales_order` (`JSON_OBJECT`), bez PHP.
  Statusy platform są mapowane na `new`, `processing`, `completed`, `cancelled`, `unfinished`; nieznane trafiają do
  `new`. Symulacja (`FakeProvisioner`) daje powtarzalne zamówienia, wyliczone z `pk` sklepu.

### Lista startowa

Pola odpowiedzi i kroki: [api.md](api.md#lista-startowa).

- Kroki wynikają z tego, co platforma już ma: ustawień zapisanych w `ShopSettings` (płatności, wysyłka), kopii
  zamówień (`ShopOrder`) i telefonów właściciela (`PushDevice`). Brakuje tylko liczby produktów, więc worker liczy je
  w sklepie (`checklist.count`) i zapisuje w `ShopChecklist` razem z tym, czy właściciel ukrył listę.
- Liczenie zleca otwarcie listy, gdy krok z produktami jest otwarty, a ostatnia próba była ponad 2 minuty temu (jak
  w sprzedaży: nieudana próba też się liczy, nic nie jest zlecane dwa razy). Gdy oba kroki z produktami są zrobione,
  sklep nie jest już liczony. Usunięcie produktów przykładowych (operacja) od razu zeruje ich liczbę.
- `count_products(shop)` w provisionerze platformy zwraca `ProductCount(products, samples)`, produkty w każdym stanie
  poza usuniętymi. WooCommerce: SQL przez `$wpdb` w `wp eval`; przykładowe to oznaczone `_sklepownia_sample` albo
  (starsze sklepy) nazwane „Przykładowy produkt N”. PrestaShop: SQL przez `Db`, przykładowe to identyfikatory
  z `SKLEPOWNIA_SAMPLE_PRODUCTS`. Magento: SQL na `catalog_product_entity`, przykładowe z `sklepownia/samples/ids`,
  bez uruchamiania konsoli Magento.
- Kroki zależą od platformy (sekcje ustawień w `platforms/__init__.py`) i od tego, czy sklep dostał produkty
  przykładowe.

### Kopie zapasowe

Przebieg: [architektura.md](architektura.md#kopie-zapasowe). Repozytorium i narzędzie:
[infra/shops/README.md](../infra/shops/README.md#kopie-zapasowe). Logika w [backups.py](../backend/shops/backups.py).

- Provisioner ma `backup(shop, tag)`, `restore_backup(shop, snapshot_id)`, `list_backups()`, `forget_backups(ids)`
  i `prune_backups()`. `ContainerProvisioner` uruchamia na nie kontener `SHOPS_BACKUP_IMAGE` z wolumenem sklepu
  (do odczytu przy kopii), repozytorium i pamięcią podręczną restic, czeka najwyżej `BACKUP_TIMEOUT` (godzina),
  czyta wynik i usuwa kontener. Platforma podaje `BACKUP_EXCLUDES` (pamięć podręczna) i `after_restore` (Magento:
  przebudowa indeksów i czyszczenie pamięci podręcznej). `FakeProvisioner` trzyma kopie w pamięci.
- Sklep bez wolumenu (np. założony symulatorem) daje `NothingToBackUp` i jest pomijany. Nieudana kopia zostaje jako
  wiersz z błędem przez 7 dni, a właściciel widzi tylko „Nie udało się zrobić kopii zapasowej…”.
- `restore(shop, backup)`: kopia `before_restore`, przywrócenie, `read_again(shop)`. Przy błędzie przywraca
  `before_restore` i zgłasza `RESTORE_FAILED`; gdy i to się nie uda, `RESTORE_BROKEN`. `read_again` czyta ustawienia
  (`operations.read_back`: także nazwa, opis, e-mail, region i motyw w `Shop`/`ShopConfig` za tym, co ma sklep),
  publikuje dokumenty, czyści kopię zamówień i `SalesSync` (pierwszy odczyt niczego nie ogłasza), zeruje liczby
  produktów listy startowej i zleca odczyt zamówień. Hasło admina wraca do zapisanego w `ShopCredentials`.
- Przechowywanie (`kept`, czas polski): wszystko z ostatniej doby, najnowsza kopia z każdego z `SHOPS_BACKUP_KEEP_DAILY`
  ostatnich dni i `SHOPS_BACKUP_KEEP_WEEKLY` tygodni (ISO), które mają kopię. Usunięty sklep: tylko najnowsza, przez
  `SHOPS_BACKUP_DELETED_DAYS` dni od jej zrobienia. Sklep z trwającą operacją jest pomijany i w kopii, i w porządkach.
- `maintain()` usuwa wiersze tylko po udanym odczycie listy z repozytorium (złe hasło kończy się błędem, nie pustą
  listą). Kopię bez wiersza przyjmuje dopiero, gdy ma ponad godzinę, żeby nie policzyć dwa razy kopii, która właśnie
  się zapisuje. Hostów innych niż `shop-<id>` nie dotyka.
- Właściciel robi najwyżej `SHOPS_BACKUP_MANUAL_PER_DAY` kopii dziennie (liczą się operacje `create_backup` od północy,
  bez nieudanych). Kopie z polecenia `backup_shops` się nie liczą.

### Strona niedziałającego sklepu

Traefik serwera sklepów wysyła adresy, pod którymi nie działa żaden kontener, na `/shop-unavailable/` z adresem
w `X-Forwarded-Host` ([infra/shops/README.md](../infra/shops/README.md#adres-bez-działającego-sklepu)).
Widok w [unavailable.py](../backend/shops/unavailable.py) szuka sklepu po slugu, gdy domena to
`SHOPS_BASE_DOMAIN` (port i wielkość liter nie mają znaczenia), i pokazuje jego nazwę z tekstem w języku sklepu
(`TEXTS`): „Wkrótce otwarcie” (`pending`, `provisioning`; `503`, `Retry-After: 300`) albo „Nieczynne” (pozostałe
stany; `503`, `Retry-After: 3600`). Usunięty sklep, inny host i brak nagłówka dają `404` „Nie ma tu sklepu”.
Odpowiedź nie trafia do pamięci podręcznej (`never_cache`), a widok przyjmuje każdą metodę bez CSRF (formularz
wysłany do zamkniętego sklepu też dostaje stronę, a widok niczego nie zmienia). Nagłówek `X-Shop-Unavailable`
(`missing`, `closed`, `opening`) odróżnia tę stronę od własnej strony sklepu: po nim monitor i czekanie na start
kontenera poznają, że Traefik nie kieruje jeszcze ruchu do sklepu.

### Kategorie

[categories.py](../backend/shops/categories.py) zwraca nazwy kategorii dla branży i liczby kategorii (1–20).
Pierwsza kategoria zastępuje domyślne „Bez kategorii” WooCommerce. Przy włączonych produktach przykładowych
powstaje 6 produktów w pierwszych trzech kategoriach.

## Aplikacja `billing`

Opis działania, stanów i operatorów: [platnosci.md](platnosci.md).

| Model | Opis |
|---|---|
| `Plan` | Cena brutto, VAT, okres w miesiącach, limit sklepów, korzyści. Migracja dodaje plan „Standard”. |
| `BillingProfile` | Dane do faktury użytkownika: osoba albo firma z NIP, adres. |
| `Subscription` | Plan użytkownika (jeden na konto): stan, okres, anulowanie, zapisana karta (token zaszyfrowany), ponowienia, zgody. |
| `Payment` | Jedna płatność: pierwsza albo odnowienie, kwota, stan, identyfikatory u operatora, opłacony okres, dane do faktury z chwili płatności. |
| `Invoice` | Faktura opłaconej płatności: numer, daty, sprzedawca i nabywca (kopie danych), kwoty netto, VAT i brutto, PDF, stan w KSeF, data wysłania e-mailem. Jak płatność zostaje po usunięciu konta. |
| `InvoiceSequence` | Ostatni numer faktury w miesiącu, dla faktur numerowanych przez platformę. |

- `services.py` prowadzi cały cykl: `start_checkout`, `apply_result` (idempotentne zastosowanie wyniku),
  `check_with_gateway`, `renew_due` i `renew`, `cancel`, `resume`. Widoki tylko je wołają.
- `invoices.py`: faktura powstaje w `_mark_paid` (`create_for`), wystawia ją `issue` przez wystawcę z `INVOICE_ISSUER`
  ([invoicing/](../backend/billing/invoicing/): `platform.py` z PDF w `pdf.py`, `fakturownia.py`; VAT w `tax.py`),
  `check_ksef` śledzi KSeF, `deliver` wysyła e-mail z PDF. PDF używa fontu DejaVu (pakiet `fonts-dejavu-core` w obrazie).
- Blokada zakładania sklepów: `shops.services.active_plan` i `paid_shop_count`; brak planu to `402`.
- Wspólny wygląd e-maili: [templates/email/](../backend/templates/email/) (`layout.html`, `rows.html`, `button.html`).

## Aplikacja `push`

Powiadomienia na telefony właścicieli. Przebieg: [architektura.md](architektura.md#powiadomienia-push), API: [api.md](api.md#powiadomienia-push-apipush).

| Model | Opis |
|---|---|
| `PushDevice` | Telefon z tokenem Expo (unikalny), platformą i modelem; `last_seen_at` odświeża każde zgłoszenie z aplikacji |
| `PushPreferences` | Tematy, o których właściciel chce wiedzieć (`new_orders`, `shops`, `billing`); bez wiersza wszystkie |
| `PushTicket` | Powiadomienie przyjęte przez usługę push, czekające na sprawdzenie potwierdzenia (receipt) |

- Inne aplikacje wołają `push.services.notify(user_id, notice)` z tekstem z [messages.py](../backend/push/messages.py).
  `notify` nic nie robi, gdy użytkownik nie ma telefonów; inaczej po zatwierdzeniu transakcji kolejkuje `send_push`.
- Wysyłkę wybiera `PUSH_SENDER`: `ExpoSender` (Expo Push API, paczki po 100, `EXPO_ACCESS_TOKEN` opcjonalnie),
  `LogSender` (tylko log) albo `MemorySender` (testy, fixture `push_outbox`). Brak odpowiedzi albo `429`/`5xx`
  od Expo to `PushUnavailable`: zadanie ponawia się z narastającym odstępem.
- `DeviceNotRegistered` w odpowiedzi albo w potwierdzeniu usuwa telefon. Inne błędy potwierdzeń (np. złe klucze
  FCM lub APNs) trafiają do logu workera jako błąd.
- Gdzie powstają powiadomienia: `shops.sales.sync` (zamówienia, które właśnie stały się sprzedażą: nowe w kopii albo
  wcześniej nieopłacone, złożone w ostatnich 7 dniach; pierwszy odczyt sklepu nic nie wysyła), `shops.tasks.provision_shop`
  (gotowy sklep, błąd zakładania), `billing.services._notify` i `_end` (nieudana opłata, koniec planu).

Nowe powiadomienie: funkcja w `messages.py` (temat, tytuł, treść, ekran aplikacji) i wywołanie `notify` w miejscu
zdarzenia. Nowy temat: wartość w `Topic`, pole w `PushPreferences` z migracją, kanał w `CHANNELS` w
[lib/push.ts](../mobile/src/lib/push.ts) i przełącznik na ekranie „Powiadomienia”.

## Aplikacja `monitoring`

Pilnuje działających sklepów i serwera sklepów. Przebieg: [architektura.md](architektura.md#monitorowanie),
obsługa: [obsluga.md](obsluga.md#monitorowanie).

| Model | Opis |
|---|---|
| `ShopHealth` | Ostatnie sprawdzenie sklepu: porażki z rzędu i od kiedy, co monitor widzi (`problem`), czy powiadomił (`alerted`), co naprawiał w tej serii (`repaired`, `repaired_at`, `repairing`), czas odpowiedzi strony głównej |
| `Incident` | Awaria: sklep (`shop:<id>`), usługa (`service:<nazwa>`), dysk, serwer (`server:<id>`) albo kopie (`backups:failed`, `backups:missing`). Najwyżej jedna otwarta na klucz; `alerted_at`, gdy obsługa dostała e-mail, `repaired`, gdy monitor sam naprawiał |
| `Heartbeat` | Ostatnia runda monitora (`monitor`) i ostatnie nocne kopie (`nightly-backups`) |

- Runda (`checks.run`, zadanie `check_shops`) bierze blokadę doradczą PostgreSQL, więc dwie naraz się nie
  nakładają. Kolejno: `service_problems` provisionera (Docker, proxy, baza sklepów, OpenSearch przy sklepach Magento,
  przekaźnik poczty, gdy jest kontenerem), sklepy (tylko gdy działają Docker, proxy i baza), `disk_space`, zapełnienie
  serwerów, wiek `Heartbeat` kopii, na koniec ping `MONITOR_PING_URL`.
- Sklepy: aktywne, bez trwającej operacji. `container_states()` daje stan kontenerów, a `check_page(shop)` odwiedza
  stronę główną przez proxy z kontenera sklepu (po kilka naraz, `MONITOR_WORKERS`). `examine` ocenia wynik: brak
  albo zatrzymany kontener to naprawa `start`, brak odpowiedzi, strona platformy (nagłówek `X-Shop-Unavailable`) albo
  status inny niż 2xx/3xx to naprawa `restart`. `503` jest w porządku w sklepie zamkniętym w ustawieniach.
- `record` liczy porażki w `ShopHealth` (z `select_for_update`). Od `MONITOR_FAILURES` z rzędu sklep nie działa
  i ma otwartą awarię. Naprawa raz na serię porażek: `start` od razu, `restart` gdy sklep nie działa. Zleca ją zadanie
  `repair_shop` (`checks.repair`), które czeka na healthcheck i routing, sprawdza stronę ponownie i dopiero gdy dalej
  źle, powiadamia. Rundy w trakcie naprawy (`repairing`, najwyżej `REPAIR_TIMEOUT`) nie liczą porażek.
- `alerts.shop_down`: push (`Topic.SHOPS`) i e-mail do właściciela bez technicznej przyczyny, e-mail do obsługi
  z tym, co widzi monitor i co naprawiał; `alerts.shop_back` po pierwszym udanym sprawdzeniu. Pozostałe awarie
  (`alerts.problem`) obsługa dostaje przy drugim sprawdzeniu z rzędu (kopie od razu) i po ich końcu (`alerts.solved`).
  Wysyłkę robią zadania po zatwierdzeniu transakcji.
- `shops.tasks.back_up_all_shops` woła `alerts.nightly_backups_done` z listą sklepów bez kopii.
- API sklepu ma `down_since`: od kiedy działający sklep nie działa, gdy właściciel już o tym wie.
- Provisioner: `can_monitor`, `container_states`, `check_page`, `start_shop`, `restart_shop`, `service_problems`,
  `disk_space` ([base.py](../backend/shops/provisioning/base.py)). `start_shop` nie zakłada pustego sklepu, gdy nie ma
  ani kontenera, ani wolumenu. `FakeProvisioner` symuluje awarie przez atrybuty klasy (`containers`, `pages`,
  `services`, `disk`, `repairs_help`) i zapisuje naprawy w `repairs`.

## Aplikacja `support`

`ContactMessage` zapisuje wiadomości z formularza kontaktowego (imię, e-mail, temat, treść, ewentualny użytkownik).
Zadanie `notify_about_contact_message` wysyła je na `CONTACT_EMAIL` z adresem nadawcy w `Reply-To`.
W panelu admina wiadomości można oznaczać jako obsłużone.

## Aplikacja `handbook`

Renderuje pliki Markdown z repozytorium jako strony pod `/docs/`, z menu sekcji.
- Lista stron i ich kolejność w menu: `PAGES` w [pages.py](../backend/handbook/pages.py).
- Pliki są czytane przy każdym wejściu na stronę z katalogu `HANDBOOK_ROOT`. W `docker-compose.yml` całe repozytorium
  jest podmontowane do kontenera backendu tylko do odczytu pod `/project`.
- Odnośniki między dokumentami prowadzą do ich stron, a odnośniki do plików z kodem są pokazywane jako zwykłe ścieżki.
- Kotwice nagłówków są takie jak na GitHubie, z polskimi znakami.
- Przy `DJANGO_DEBUG=0` strony czytają tylko administratorzy (`is_staff`); pozostali trafiają na logowanie do panelu.

## Zadania Celery

| Zadanie | Kiedy | Co robi |
|---|---|---|
| `accounts.tasks.send_verification_email` | Rejestracja, ponowne wysłanie kodu | Wysyła kod potwierdzający |
| `shops.tasks.provision_shop` | Założenie i ponowienie sklepu | Wykonuje kroki zadania (`run_job`) |
| `shops.tasks.teardown_shop` | Usunięcie sklepu albo konta | Robi kopię „Stan sprzed usunięcia sklepu” (bez niej, gdy się nie uda), usuwa kontener, wolumen i bazę; przy usuniętym koncie bez kopii, a potem usuwa kopie i wiersz sklepu |
| `shops.tasks.back_up_all_shops` | Co noc o `SHOPS_BACKUP_HOUR` (Celery beat) | Kopia każdego działającego i zawieszonego sklepu, potem porządki w repozytorium (`backups.back_up_all`); monitor dostaje listę nieudanych |
| `accounts.tasks.send_account_deleted_email` | Usunięcie konta | Potwierdzenie na dawny adres z listą usuniętych sklepów |
| `shops.tasks.send_admin_access_email` | Koniec zakładania, nowe hasło, prośba z aplikacji | Wysyła właścicielowi e-mail ze szczegółami sklepu i danymi logowania ([emails.py](../backend/shops/emails.py)); przy błędzie serwera pocztowego ponawia |
| `billing.tasks.renew_subscriptions` | Co 15 minut (Celery beat) | Odnawia plany, ponawia nieudane odnowienia, kończy anulowane i niezapłacone |
| `billing.tasks.reconcile_payments` | Co 5 minut (Celery beat) | Pyta operatora o płatności, które wciąż czekają; po dobie oznacza je jako niedokończone |
| `billing.tasks.issue_invoice` | Po opłaceniu płatności | Wystawia fakturę (numer, PDF, wysyłka do KSeF przez Fakturownię) |
| `billing.tasks.deliver_invoice` | Gdy faktura jest gotowa | Wysyła ją e-mailem z PDF; ponawia przy błędzie SMTP |
| `billing.tasks.process_invoices` | Co 5 minut (Celery beat) | Ponawia nieudane wystawienia, pyta o stan w KSeF, wysyła faktury, których e-mail nie wyszedł |
| `billing.tasks.send_billing_email` | Opłacona płatność, nieudane odnowienie, koniec planu | Wysyła e-mail o planie i płatności |
| `shops.tasks.run_shop_operation` | Zmiana i odczyt ustawień, nowe hasło, usunięcie produktów przykładowych, kopia i jej przywrócenie | Wykonuje operację (`run_operation`) |
| `support.tasks.notify_about_contact_message` | Wysłanie formularza kontaktowego | Przekazuje wiadomość e-mailem |
| `shops.tasks.sync_all_shop_orders` | Co `SHOP_ORDERS_SYNC_MINUTES` minut, domyślnie 15 (Celery beat) | Zleca odczyt zamówień działających sklepów, które nie były czytane od pół interwału |
| `shops.tasks.sync_shop_orders` | Harmonogram, otwarcie podsumowania sprzedaży albo listy startowej, przycisk „Odśwież” | Kopiuje zmienione zamówienia sklepu (`sales.sync`) i powiadamia o nowych |
| `shops.tasks.count_shop_products` | Otwarcie listy startowej z otwartym krokiem produktów | Liczy własne i przykładowe produkty w sklepie (`checklist.count`) |
| `push.tasks.send_push` | Nowe zamówienie, koniec zakładania sklepu, nieudana opłata, koniec planu | Wysyła powiadomienie na telefony użytkownika; ponawia, gdy Expo nie odpowiada |
| `push.tasks.check_push_receipts` | Co 15 minut (Celery beat) | Sprawdza potwierdzenia wysłanych powiadomień, usuwa telefony bez aplikacji |
| `monitoring.tasks.check_shops` | Co `MONITOR_INTERVAL_MINUTES` minut, domyślnie 5 (Celery beat; runda czekająca dłużej w kolejce przepada) | Runda monitora (`checks.run`) |
| `monitoring.tasks.repair_shop` | Runda znalazła zatrzymany albo nieodpowiadający sklep | Uruchamia albo restartuje kontener, sprawdza sklep ponownie, przy dalszej awarii powiadamia |
| `monitoring.tasks.send_shop_email` | Sklep nie działa, znowu działa | E-mail do właściciela; ponawia przy błędzie SMTP |
| `monitoring.tasks.send_staff_alert` | Awaria i jej koniec | E-mail na `ALERT_EMAILS`; ponawia przy błędzie SMTP |

Zadania są kolejkowane przez `transaction.on_commit`, więc worker nigdy nie widzi niezatwierdzonych danych.
Worker potwierdza zadanie dopiero po jego wykonaniu (`CELERY_TASK_ACKS_LATE`) i bierze naraz jedno
(`CELERY_WORKER_PREFETCH_MULTIPLIER = 1`).

## Polecenia

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec worker  python manage.py update_shop_addresses   # po zmianie SHOPS_BASE_DOMAIN
docker compose exec worker  python manage.py configure_shop_mail     # poczta w sklepach sprzed niej albo po zmianie SHOPS_SMTP_*
docker compose exec backend python manage.py publish_shop_documents  # nowa wersja wzorów regulaminu w sklepach
docker compose exec worker  python manage.py backup_shops [slug…]     # kopie zapasowe teraz
docker compose exec worker  python manage.py restore_shop <id|slug> [--backup N]   # przywrócenie, też usuniętego sklepu
docker compose exec worker  python manage.py check_shops [slug…]      # runda monitora teraz
docker compose exec worker  python manage.py update_shop_containers [slug…] [--dry-run]   # kontenery jak nowe (np. z healthcheckiem)
docker compose exec worker  python manage.py connect_shop_api [slug…] [--check]   # nowy klucz API sklepu i test połączenia
docker compose exec backend python manage.py spectacular --file schema.yml   # schemat OpenAPI do pliku
```

`update_shop_addresses` uruchamia się w workerze, bo tylko on ma dostęp do Dockera.
Dla każdego działającego sklepu odtwarza kontener z nową regułą Traefika i podmienia adres w bazie WordPressa.

`configure_shop_mail [slug…]` ustawia w działających sklepach wysyłkę przez przekaźnik poczty
([poczta sklepów](../infra/shops/README.md#poczta-sklepów)). Nowe sklepy dostają ją przy zakładaniu.
Kontener ze starszego obrazu jest najpierw odtwarzany. Zawieszone sklepy są pomijane, bo ich kontenery stoją.

`publish_shop_documents [slug…] [--all]` zleca operację `publish_documents` w działających sklepach, które mają
regulamin z aplikacji w starszej wersji wzorów niż `documents.VERSION` (z `--all`: wszystkich takich sklepach).
Publikuje worker, więc polecenie działa w każdym kontenerze backendu. Sklep zajęty inną operacją jest pomijany
z komunikatem; wystarczy uruchomić polecenie jeszcze raz.

`backup_shops` i `restore_shop` opisuje [obsluga.md](obsluga.md#kopie-zapasowe), `check_shops`
i `update_shop_containers` [obsluga.md](obsluga.md#monitorowanie), a `connect_shop_api`
[obsluga.md](obsluga.md#połączenie-aplikacji-ze-sklepem).

## Panel admina

http://localhost:8000/admin/ (konto z `createsuperuser`). Zawiera:

- **Użytkowników:** potwierdzenie e-maila, uprawnienia.
- **Serwery i szablony:** motywy można wyłączać i ustawiać ich kolejność w formularzu.
- **Sklepy z konfiguracją:** status jest tylko do odczytu. Zmienia się go przez serwisy, nie przez formularz.
- **Zadania zakładania:** podgląd kroków i błędów.
- **Operacje na sklepach:** historia zmian ustawień i innych operacji, ze zmienionymi polami i błędami (bez kluczy płatności).
- **Kopie zapasowe sklepów** (Shop backups): rodzaj, stan, rozmiar, snapshot i błąd nieudanych kopii, tylko do odczytu.
- **Monitorowanie:** awarie (trwające i zakończone, z czasem trwania i naprawą), stan sklepów (ostatnie sprawdzenie,
  co monitor widzi, czas odpowiedzi) i ostatnie uruchomienia rundy i nocnych kopii, tylko do odczytu.
- **Wiadomości kontaktowe.**

## Testy

```bash
docker compose exec backend pytest          # wszystkie testy
docker compose exec backend pytest --cov    # z pokryciem kodu (ustawienia w backend/.coveragerc)
```

Testy (pytest-django) używają symulowanego provisionera i wykonują zadania Celery od razu (`task_always_eager`).
Pobieranie wtyczek z sieci jest w testach zablokowane: test, który go potrzebuje, podstawia `packages._download`.
Ustawienia testowe są w [conftest.py](../backend/conftest.py) i nie zależą od lokalnego `.env`
(np. domena sklepów to zawsze `localhost`).

| Plik | Co sprawdza |
|---|---|
| `accounts/tests/test_auth.py` | Rejestracja, logowanie, potwierdzanie e-maila, limity prób, `/me` |
| `shops/tests/test_shops.py` | Zakładanie, limit sklepów, adresy, ponawianie, usuwanie, dostęp do panelu, opcje formularza, polecenia |
| `shops/tests/test_settings.py` | Ustawienia sklepu: odczyt, walidacja, zapis przez operacje, kolejka jednej operacji, błędy, nowe hasło, produkty przykładowe |
| `shops/tests/test_documents.py` | Regulamin i polityka prywatności: dane z faktur, publikacja przy włączeniu i po zmianach, wymagane pola i formaty, tylko Polska, podgląd, treść wzorów, polecenie `publish_shop_documents`, krok listy startowej |
| `shops/tests/test_online_payments.py` | Płatności online w ustawieniach: klucze tylko w drodze do sklepu (szyfrowane, czyszczone, ukryte w historii), wymagane pola, nowy tryb, format, Magento |
| `shops/tests/test_backups.py` | Kopie zapasowe: lista i limit kopii właściciela, przywrócenie z kopią stanu sprzed niego i powrotem po błędzie, odczyt sklepu po przywróceniu, noc, przechowywanie, uzgadnianie z repozytorium, usunięcie sklepu i konta, polecenia, kontener narzędzia restic |
| `shops/tests/test_packages.py` | Pobieranie wtyczek: jedno pobranie i pamięć podręczna, odrzucenie pliku o innej sumie, uszkodzona kopia, brak sieci |
| `shops/tests/test_woocommerce.py` | Polecenia, które `WooCommerceProvisioner` wysyła do kontenerów (WP-CLI, MariaDB, curl), na podstawionej powłoce bez Dockera |
| `shops/tests/test_prestashop.py` | To samo dla `PrestaShopProvisioner`: instalator, skrypty PHP i ich dane, sprawdzenie sklepu i panelu |
| `shops/tests/test_magento.py` | To samo dla `MagentoProvisioner`: `setup:install`, akcje `sklepownia:run` i ich dane, pamięć, indeksy OpenSearch |
| `shops/tests/test_platforms.py` | Platformy przez API: wybór motywu i platformy, kroki, panel, sekcje ustawień, wybór provisionera |
| `billing/tests/test_billing.py`, `billing/tests/test_tpay.py` | Płatności i bramka Tpay ([platnosci.md](platnosci.md#testy)) |
| `shops/tests/test_emails.py` | E-mail z danymi logowania: po założeniu i ponowieniu, ponowne wysłanie i jego limit, nowe hasło, brak danych w API, uwaga o ustawieniach zgodna z sekcjami aplikacji na każdej platformie |
| `shops/tests/test_unavailable.py` | Strona pod adresem niedziałającego sklepu: zawieszony i zakładany (kod, `Retry-After`, szyld), język sklepu, nieznane i obce adresy, usunięty sklep, formularz bez CSRF |
| `shops/tests/test_commands.py` | Polecenia `update_shop_addresses` i `configure_shop_mail`, domyślne zachowanie `BaseProvisioner` |
| `support/tests/test_contact.py` | Formularz kontaktowy i powiadomienie |
| `handbook/tests/test_handbook.py` | Strony dokumentacji, odnośniki, kotwice, dostęp, kompletność menu |

Testy platform (`test_woocommerce.py`, `test_prestashop.py`, `test_magento.py`) zastępują `_exec` atrapą (`Shell`), która zapisuje polecenia i odpowiada
przygotowanym wynikiem. Sprawdzają więc, co provisioner wysyła i jak czyta odpowiedzi, ale nie to, czy sklep
się z nimi zgodzi. Zmiany w provisioningu trzeba dodatkowo sprawdzić na prawdziwym sklepie.

Zmiany w API sprawdzaj też walidacją schematu: `python manage.py spectacular --validate --fail-on-warn`.
