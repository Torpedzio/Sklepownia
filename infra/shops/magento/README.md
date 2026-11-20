# Sklepy Magento

Sklepy Magento działają na dystrybucji [Mage-OS](https://mage-os.org/) 4.0 (Magento Open Source bez kluczy Adobe)
w obrazie `shops/magento:4.0.0` z [Dockerfile](Dockerfile). Backend: [magento.py](../../../backend/shops/platforms/magento.py).

```bash
cd infra/shops
docker compose build magento     # ~10 min: Composer, kompilacja DI, pliki statyczne
docker compose up -d search      # OpenSearch, potrzebny każdemu sklepowi Magento
```

## Jak to działa

- **Kod w obrazie, dane w wolumenie.** Obraz ma gotowy kod: moduły z Composera, polskie tłumaczenie
  (`community-engineering/language-pl_pl`), skompilowane klasy (`setup:di:compile`) i pliki statyczne motywów Luma
  i panelu (Mage-OS `MageOS/m137-admin-theme` i `Magento/backend`) dla `pl_PL`, `en_US`, `de_DE`. Wolumen `shop-<id>` jest na `/var/www/data` i trzyma tylko dane sklepu:
  `env.php` (hasła, adres panelu), `media/` (zdjęcia) i `var/` (pamięć podręczna, sesje, logi).
  Obraz wskazuje na nie dowiązaniami ([entrypoint.sh](entrypoint.sh) tworzy brakujące katalogi przy starcie).
  Dzięki temu nowy obraz (np. z poprawkami bezpieczeństwa) to tylko nowy kontener.
- **Budowanie bez bazy.** Kompilacja i pliki statyczne potrzebują sklepów i motywów, które normalnie są w bazie.
  [build-config.php](build-config.php) wpisuje je na czas budowania do `app/etc/config.php` i potem usuwa,
  żeby każdy sklep miał je we własnej bazie i właściciel mógł je zmieniać w panelu.
- **Nasz moduł** [Sklepownia/Provisioning](Sklepownia/Provisioning/) dodaje polecenie `bin/magento sklepownia:run <akcja>`:
  `catalog` (kategorie i przykładowe produkty), `home` (strona główna), `read` (ustawienia dla aplikacji), `config`
  (zapis ustawień), `taxes` (stawka i reguła VAT), `admin` (e-mail, hasło i język panelu administratora),
  `remove_samples`, `documents` (regulamin i polityka prywatności jako strony CMS, zgoda na regulamin przy
  zamówieniu). Dane przychodzą jako base64 JSON w zmiennej `SKLEPOWNIA_DATA` (hasła nie trafiają na listę procesów),
  wynik to JSON po znaczniku `@@sklepownia@@`. Moduł dodaje też metodę dostawy „Odbiór osobisty” (`sklepowniapickup`)
  i wtyczkę [MailSender](Sklepownia/Provisioning/Plugin/MailSender.php), która wysyła pocztę sklepu z adresu
  platformy ([poczta sklepów](../README.md#poczta-sklepów)). Layout modułu
  ([default.xml](Sklepownia/Provisioning/view/frontend/layout/default.xml)) dodaje do stopki link „Regulamin”,
  widoczny, gdy sklep ma regulamin z aplikacji (`sklepownia/documents/terms_link`). Zmiana w module wymaga przebudowy
  obrazu (`docker compose build magento`), a działające sklepy dostają nowy obraz przy `configure_shop_mail` i przy
  publikacji regulaminu.
- **Wyszukiwarka:** jeden OpenSearch (`shops-search`) dla wszystkich sklepów; każdy ma swoje indeksy z prefiksem
  `shop_<id>`, usuwane razem ze sklepem.
- **Zadania okresowe** (indeksy, e-maile, ceny) uruchamia co minutę pętla w [entrypoint.sh](entrypoint.sh),
  dopiero po zakończonej instalacji (data instalacji w `env.php`).
- **Pamięć:** sklep dostaje co najmniej `SHOPS_MAGENTO_MEMORY` (1536 MB), nawet gdy plan daje mniej.

## Kroki i czasy

Baza i miejsce na serwerze jak w [README serwera](../README.md). Czasy z laptopa, sklep z 5 kategoriami i przykładowymi produktami.

| Krok | Co robi | Czas |
|---|---|---|
| Uruchomienie sklepu | kontener z wolumenem na `/var/www/data`; gotowy, gdy są katalogi danych i Apache odpowiada | ~3 s |
| Sklep, język i konto administratora | `setup:install` z adresem, bazą, OpenSearch, językiem, walutą, strefą czasową i losowym adresem panelu (`admin_<znaki>` w `Shop.admin_path`); tryb produkcyjny bez ponownej kompilacji; e-mail, hasło i język panelu administratora `admin`; przeładowanie Apache | ~35 s |
| Waluta, płatności i dostawa | nazwa, e-maile nadawcy, opis; wyłączenie płatności czekiem, przelewem i przy odbiorze oraz wszystkich dostaw; kurier za zamówienie, nie za sztukę; nazwy płatności i dostaw w języku sklepu; strona główna z nazwą, opisem i najnowszymi produktami; nazwa sklepu zamiast napisów Luma | ~2 s |
| Kategorie produktów | kategorie pod kategorią główną sklepu i opcjonalnie 6 przykładowych produktów | ~2 s |
| Menu, wyszukiwarka i filtry | Luma sama pokazuje kategorie w menu i filtry w kategoriach; `indexer:reindex` buduje indeksy wyszukiwarki i filtrów | ~3 s |
| Połączenie z aplikacją | `sklepownia:run api`: integracja `Sklepownia` z dostępem do wszystkiego (poprzednia o tej nazwie jest usuwana) i jej token; tokeny integracji jako Bearer (`oauth/consumer/enable_integration_as_bearer`) | ~3 s |
| Końcowe sprawdzenie | strona główna, wyniki wyszukiwania i strona logowania panelu przez proxy, wszystkie 200; backend pod adresem sklepu odczytuje `V1/store/storeViews` z tokenem | ~4 s |
| **Razem** | | **~50 s** |

Z aplikacji zmienia się podstawowe dane, płatności, wysyłkę, podatki i region.
Otwarcie sklepu, zasady zakupów i motyw zmienia się w panelu Magento.

## Uwagi techniczne

- **Mage-OS a moduły:** Mage-OS nie ma modułów Adobe IMS, a jego logowanie kluczem dostępu (`MageOS_PasskeyAuth`)
  wymaga dwuetapowego logowania. Wyłączamy oba razem z `Magento_AdminAnalytics` i `Magento_ReleaseNotification`;
  Dockerfile wyłącza tylko te, które są w danej wersji.
- **Dwuetapowe logowanie** do panelu jest wyłączone: panel ma losowy adres, a hasłem zarządza platforma
  („Nowe hasło” w aplikacji).
- **Ustawienia** zapisujemy w zakresie domyślnym i usuwamy nadpisania z zakresu strony i widoku sklepu,
  żeby zmiana z aplikacji zawsze była widoczna. Nadpisania ustawione w panelu dla innych sklepów (multistore) zostają.
- **Przelew:** Magento ma tylko pole „Instrukcje”; budujemy je z odbiorcy, numeru konta i banku w języku sklepu,
  a same dane trzymamy w `sklepownia/bank/*`, żeby aplikacja mogła je pokazać.
- **Nazwy dostaw i płatności** Magento trzyma jako zwykłe ustawienia bez tłumaczeń, więc zmiana języka je podmienia.
- **Adres** sklepu to `web/unsecure/base_url` i `web/secure/base_url`; `update_shop_addresses` podmienia oba.
- **Apache po instalacji:** serwer WWW pamięta sklep sprzed instalacji (bez `env.php`) i odsyła na `/setup/`,
  dopóki się nie przeładuje. Krok instalacji kończy się więc `apachectl -k graceful`. Pliki z `/var/www/data`
  i `app/etc/env.php` są wyłączone z opcache ([php.ini](php.ini), `opcache-blacklist.txt`), bo zmieniają się
  w działającym sklepie (np. ustawienia pamięci podręcznej w panelu), a reszta kodu jest stała
  (`opcache.validate_timestamps=0`).
- **Adres https:** `setup:install` przyjmuje `--base-url-secure` tylko z `https://`, więc lokalnie (http) go nie podajemy.
- **Kategorie** zapisujemy przez `CategoryRepository` z samym `parent_id`; ścieżkę (`1/2/<id>`) liczy Magento.
  Ustawiona ręcznie ścieżka rodzica daje kategorie, których nie widać w menu.
- **Usuwanie produktów** z wiersza poleceń wymaga flagi `isSecureArea` w rejestrze, tak jak w panelu.
- **Napisy Luma:** „Domyślna wiadomość powitalna!” w nagłówku i stopka „Copyright … Magento” są zastępowane nazwą sklepu.
  Logo Luma zostaje do wymiany w panelu (Treść → Projekt → Konfiguracja).
