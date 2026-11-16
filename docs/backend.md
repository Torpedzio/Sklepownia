# Backend

Django 5.2 + Django REST Framework, Celery z Redisem, PostgreSQL. Kod w [backend/](../backend/).

## Struktura

```
backend/
├── config/            ustawienia, główne URL-e, konfiguracja Celery
├── accounts/          użytkownicy, rejestracja, logowanie JWT, potwierdzanie e-maila
├── shops/             sklepy: modele, API, zakładanie (provisioning), polecenia
│   ├── platforms/     __init__.py (platformy: kroki, sekcje ustawień, panel), woocommerce.py, prestashop.py, magento.py
│   ├── provisioning/  base.py (kroki), container.py (wspólne dla kontenerów), runner.py (zakładanie),
│   │                  operations.py (operacje na działającym sklepie), fake.py (symulacja)
│   ├── management/    polecenie update_shop_addresses
│   ├── categories.py  nazwy kategorii według branży
│   ├── emails.py      e-mail z danymi sklepu i logowaniem (szablony w templates/shops/email/)
│   ├── choices.py     branże, języki, waluty, kraje, zakres liczby kategorii
│   ├── fields.py      EncryptedTextField (szyfrowanie Fernet)
│   ├── services.py    create_shop, retry_shop, delete_shop, get_settings, update_settings, start_operation
│   ├── shop_settings.py  sekcje ustawień sklepu: pola, etykiety, walidacja, wartości domyślne
│   └── slugs.py       zasady adresów sklepów i lista zarezerwowanych
├── billing/           plany, dane do faktury, płatności, odnowienia, operatorzy płatności (gateways/)
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
- **`GET /api/auth/me/`** zwraca dane konta razem z `shop_limit`, żeby aplikacja mogła zablokować przycisk nowego sklepu.

## Aplikacja `shops`

### Modele

| Model | Opis |
|---|---|
| `Server` | Serwer, na którym działają kontenery sklepów, z limitem `max_shops`. Migracja tworzy serwer `local`. |
| `ShopTemplate` | Motyw do wyboru w formularzu, dla jednej platformy (`platform`). `theme` to nazwa motywu w systemie sklepu. Migracje dodają Storefront, Astrę i Kadence (WooCommerce) oraz Hummingbird i Classic (PrestaShop). |
| `Shop` | Sklep: właściciel, nazwa, `slug` (część adresu), platforma, status z maszyną stanów, serwer. `url` i `admin_url` są liczone z ustawień; folder panelu PrestaShop jest w `admin_path`. |
| `ShopConfig` | Wybory z formularza: branża, motyw, liczba kategorii, język, waluta, kraj, e-mail, produkty przykładowe. Zmiany z ustawień (opis, e-mail, język, waluta, kraj, motyw) są tu dopisywane. |
| `ShopCredentials` | Login administratora (`admin_login`: nazwa użytkownika w WordPressie, e-mail w PrestaShop) i hasła: bazy, administratora, API WordPressa. Hasła zaszyfrowane. |
| `ProvisioningJob` | Jedna próba założenia sklepu (status, błąd, czasy). Ponowienie tworzy nowe zadanie. |
| `ProvisioningStep` | Krok zadania: klucz, etykieta dla użytkownika, status, błąd, czasy. |
| `ShopSettings` | Ostatnio odczytane albo zapisane ustawienia sklepu (`values`, JSON w sekcjach) i czas odczytu ze sklepu. |
| `ShopOperation` | Praca na działającym sklepie: zmiana ustawień, odczyt ustawień, nowe hasło, usunięcie produktów przykładowych. Zmienione pola, wynik, błąd, kto zlecił. Służy też jako historia zmian. |

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
  wolumen `shop-<id>` i bazę `shop_<id>`. Na nim stoją:
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

- `services.py` prowadzi cały cykl: `start_checkout`, `apply_result` (idempotentne zastosowanie wyniku),
  `check_with_gateway`, `renew_due` i `renew`, `cancel`, `resume`. Widoki tylko je wołają.
- Blokada zakładania sklepów: `shops.services.active_plan` i `paid_shop_count`; brak planu to `402`.
- Wspólny wygląd e-maili: [templates/email/](../backend/templates/email/) (`layout.html`, `rows.html`, `button.html`).

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
| `shops.tasks.teardown_shop` | Usunięcie sklepu | Usuwa kontener, wolumen i bazę |
| `shops.tasks.send_admin_access_email` | Koniec zakładania, nowe hasło, prośba z aplikacji | Wysyła właścicielowi e-mail ze szczegółami sklepu i danymi logowania ([emails.py](../backend/shops/emails.py)); przy błędzie serwera pocztowego ponawia |
| `billing.tasks.renew_subscriptions` | Co 15 minut (Celery beat) | Odnawia plany, ponawia nieudane odnowienia, kończy anulowane i niezapłacone |
| `billing.tasks.reconcile_payments` | Co 5 minut (Celery beat) | Pyta operatora o płatności, które wciąż czekają; po dobie oznacza je jako niedokończone |
| `billing.tasks.send_billing_email` | Opłacona płatność, nieudane odnowienie, koniec planu | Wysyła e-mail o planie i płatności |
| `shops.tasks.run_shop_operation` | Zmiana i odczyt ustawień, nowe hasło, usunięcie produktów przykładowych | Wykonuje operację (`run_operation`) |
| `support.tasks.notify_about_contact_message` | Wysłanie formularza kontaktowego | Przekazuje wiadomość e-mailem |

Zadania są kolejkowane przez `transaction.on_commit`, więc worker nigdy nie widzi niezatwierdzonych danych.
Worker potwierdza zadanie dopiero po jego wykonaniu (`CELERY_TASK_ACKS_LATE`) i bierze naraz jedno
(`CELERY_WORKER_PREFETCH_MULTIPLIER = 1`).

## Polecenia

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec worker  python manage.py update_shop_addresses   # po zmianie SHOPS_BASE_DOMAIN
docker compose exec backend python manage.py spectacular --file schema.yml   # schemat OpenAPI do pliku
```

`update_shop_addresses` uruchamia się w workerze, bo tylko on ma dostęp do Dockera.
Dla każdego działającego sklepu odtwarza kontener z nową regułą Traefika i podmienia adres w bazie WordPressa.

## Panel admina

http://localhost:8000/admin/ (konto z `createsuperuser`). Zawiera:

- **Użytkowników:** potwierdzenie e-maila, uprawnienia.
- **Serwery i szablony:** motywy można wyłączać i ustawiać ich kolejność w formularzu.
- **Sklepy z konfiguracją:** status jest tylko do odczytu. Zmienia się go przez serwisy, nie przez formularz.
- **Zadania zakładania:** podgląd kroków i błędów.
- **Operacje na sklepach:** historia zmian ustawień i innych operacji, ze zmienionymi polami i błędami.
- **Wiadomości kontaktowe.**

## Testy

```bash
docker compose exec backend pytest          # wszystkie testy
docker compose exec backend pytest --cov    # z pokryciem kodu (ustawienia w backend/.coveragerc)
```

Testy (pytest-django) używają symulowanego provisionera i wykonują zadania Celery od razu (`task_always_eager`).
Ustawienia testowe są w [conftest.py](../backend/conftest.py) i nie zależą od lokalnego `.env`
(np. domena sklepów to zawsze `localhost`).

| Plik | Co sprawdza |
|---|---|
| `accounts/tests/test_auth.py` | Rejestracja, logowanie, potwierdzanie e-maila, limity prób, `/me` |
| `shops/tests/test_shops.py` | Zakładanie, limit sklepów, adresy, ponawianie, usuwanie, dostęp do panelu, opcje formularza, polecenia |
| `shops/tests/test_settings.py` | Ustawienia sklepu: odczyt, walidacja, zapis przez operacje, kolejka jednej operacji, błędy, nowe hasło, produkty przykładowe |
| `shops/tests/test_woocommerce.py` | Polecenia, które `WooCommerceProvisioner` wysyła do kontenerów (WP-CLI, MariaDB, curl), na podstawionej powłoce bez Dockera |
| `shops/tests/test_prestashop.py` | To samo dla `PrestaShopProvisioner`: instalator, skrypty PHP i ich dane, sprawdzenie sklepu i panelu |
| `shops/tests/test_magento.py` | To samo dla `MagentoProvisioner`: `setup:install`, akcje `sklepownia:run` i ich dane, pamięć, indeksy OpenSearch |
| `shops/tests/test_platforms.py` | Platformy przez API: wybór motywu i platformy, kroki, panel, sekcje ustawień, wybór provisionera |
| `billing/tests/test_billing.py`, `billing/tests/test_tpay.py` | Płatności i bramka Tpay ([platnosci.md](platnosci.md#testy)) |
| `shops/tests/test_emails.py` | E-mail z danymi logowania: po założeniu i ponowieniu, ponowne wysłanie i jego limit, nowe hasło, brak danych w API |
| `shops/tests/test_commands.py` | Polecenie `update_shop_addresses` i domyślne zachowanie `BaseProvisioner` |
| `support/tests/test_contact.py` | Formularz kontaktowy i powiadomienie |
| `handbook/tests/test_handbook.py` | Strony dokumentacji, odnośniki, kotwice, dostęp, kompletność menu |

Testy platform (`test_woocommerce.py`, `test_prestashop.py`, `test_magento.py`) zastępują `_exec` atrapą (`Shell`), która zapisuje polecenia i odpowiada
przygotowanym wynikiem. Sprawdzają więc, co provisioner wysyła i jak czyta odpowiedzi, ale nie to, czy sklep
się z nimi zgodzi. Zmiany w provisioningu trzeba dodatkowo sprawdzić na prawdziwym sklepie.

Zmiany w API sprawdzaj też walidacją schematu: `python manage.py spectacular --validate --fail-on-warn`.
