# API

Pełna, zawsze aktualna specyfikacja generuje się z kodu (drf-spectacular):

- http://localhost:8000/api/docs/: Swagger. Przycisk „Authorize” przyjmuje token dostępu (`Bearer <access>`).
- http://localhost:8000/api/schema/: schemat OpenAPI 3 (YAML), np. do generowania klientów.

Ten plik jest przeglądem: co jest gdzie i jakie obowiązują zasady.

## Zasady

- Format: JSON. Adres bazowy: `http://<host>:8000/api`.
- Uwierzytelnianie: nagłówek `Authorization: Bearer <access>`. Domyślnie każdy endpoint wymaga zalogowania,
  wyjątki są oznaczone niżej.
- Token dostępu wygasa po 30 minutach. Wtedy `POST /api/auth/refresh/` z tokenem odświeżania zwraca nową parę.
  Stary token odświeżania przestaje działać (rotacja).
- Błędy walidacji: `400` z obiektem `{pole: ["komunikat"]}`. Błędy ogólne: `{"detail": "komunikat"}`.
  Komunikaty są po polsku i nadają się do pokazania użytkownikowi.
- Konflikt stanu sklepu (np. usuwanie w trakcie zakładania): `409` z `detail`.
- Przekroczenie limitu zapytań: `429`.

## Konta: `/api/auth/`

| Metoda i ścieżka | Logowanie | Opis |
|---|---|---|
| `POST register/` | nie | `{email, password, purpose?}` → `201 {user, tokens}`. Wysyła kod potwierdzający. `purpose`: `own_shop` (domyślnie, zakłada własne sklepy) albo `team` (dołącza do zespołów cudzych sklepów); decyduje tylko o tym, co proponuje aplikacja. |
| `POST login/` | nie | `{email, password}` → `{access, refresh}`. Wielkość liter w e-mailu nie ma znaczenia. |
| `POST refresh/` | nie | `{refresh}` → `{access, refresh}` |
| `POST logout/` | tak | `{refresh}` → `205`. Unieważnia token odświeżania. |
| `POST logout-everywhere/` | tak | `205`. Unieważnia wszystkie tokeny odświeżania konta: wylogowanie na każdym urządzeniu. |
| `POST change-password/` | tak | `{current_password, new_password}` → `{access, refresh}`. Inne urządzenia są wylogowane, to dostaje nowe tokeny, a właściciel e-mail o zmianie. `400` przy złym obecnym albo słabym nowym haśle. |
| `POST password-reset/` | nie | `{email}` → `204`. Wysyła kod do ustawienia nowego hasła (ważny 15 min). Odpowiedź jest taka sama dla adresu bez konta i dla ponownej prośby w ciągu 60 s (wtedy nic nie wychodzi), żeby nie dało się sprawdzać, kto ma konto. |
| `POST password-reset/confirm/` | nie | `{email, code, new_password}` → `{access, refresh}`: nowe hasło i od razu zalogowanie. Inne urządzenia są wylogowane, właściciel dostaje e-mail o zmianie, a niepotwierdzony adres staje się potwierdzony (kod dowodzi dostępu do skrzynki). `400` z `{code: [...]}` przy złym, wygasłym albo zablokowanym kodzie (5 prób; dla nieznanego adresu ten sam komunikat) albo `{new_password: [...]}` przy słabym haśle, po którym kod dalej działa. |
| `POST delete-account/` | tak | `{password}` → `204`. Usuwa konto ze wszystkimi sklepami: plan kończy się od razu (bez zwrotu za resztę okresu), karta, dane do faktury i zdjęcie znikają, a konto zostaje zanonimizowane i wylogowane wszędzie. Opłacone płatności zostają dla przepisów podatkowych. Na dawny adres idzie potwierdzenie z listą usuniętych sklepów, a adres jest od razu wolny. `400` z `{password: [...]}` przy złym haśle; `409 {detail}`, gdy sklep jest w kolejce albo właśnie zakładany, albo dla konta administratora (to usuwa się w panelu). |
| `GET me/` | tak | Dane konta: `id, email, first_name, last_name, is_email_verified, date_joined, shop_limit, magento_shop_limit, plan, can_create_shops, avatar_url, purpose` |
| `PATCH me/` | tak | Zmiana `first_name`, `last_name`, `purpose` |
| `PUT avatar/` | tak | `multipart/form-data` z polem `avatar` (JPG, PNG, WebP albo GIF do 10 MB) → dane konta. Serwer przycina zdjęcie do kwadratu 512×512, zapisuje jako WebP bez metadanych (EXIF, GPS) i usuwa poprzednie. `400` z `{avatar: [...]}`, gdy plik nie jest obsługiwanym zdjęciem. |
| `DELETE avatar/` | tak | Usuwa zdjęcie profilowe → dane konta z `avatar_url: null`. |
| `POST verify-email/` | tak | `{code}` (6 cyfr) → dane konta z `is_email_verified: true` |
| `POST resend-verification/` | tak | `204`. Nowy kod najwcześniej po 60 s, inaczej `429`. |

Limity zapytań: logowanie, rejestracja i ustawianie nowego hasła 10 na minutę, potwierdzanie e-maila 10 na godzinę, prośby o kod do nowego hasła 5 na godzinę z jednego adresu IP, zmiana zdjęcia profilowego 30 na godzinę.

## Sklepy: `/api/shops/`

Obsługa sklepu (`role: staff`) może tylko oglądać sklep (`GET shops/`, `GET shops/{id}/`), sprzedaż (`sales/`, `sales/refresh/`) i zamówienia (`orders/`, `orders/{order_id}/`, także ich obsługę: `actions/` i notatki), produkty (`products/`, także zmianę stanu) oraz opuścić zespół (`leave/`). Pozostałe akcje na sklepie dają jej `403` z „Tylko właściciel sklepu może to zrobić.”. Osoba spoza sklepu dostaje `404`.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/` | Sklepy użytkownika, własne i te, które obsługuje (bez usuniętych): `id, name, slug, url, status, status_display, platform, platform_display, is_test, created_at, down_since, role`. `role`: `owner` (właściciel) albo `staff` (obsługa). `platform`: `woocommerce`, `prestashop` albo `magento`. `is_test`: sklep sprzed płatnych planów. `down_since`: od kiedy działający sklep nie odpowiada klientom (gdy monitor już powiadomił właściciela), inaczej `null` |
| `POST shops/` | Założenie sklepu (wymaga potwierdzonego e-maila i aktywnego planu). `201` ze szczegółami sklepu. `402` bez planu, `400` przy zajętym adresie albo osiągniętym limicie planu (sklepy testowe się nie liczą); limit sklepów Magento daje błąd pola `platform`. |
| `GET shops/{id}/` | Szczegóły: pola z listy plus `panel_name` (np. „panel PrestaShop”), `setup_time` (ile trwa zakładanie, np. „około dwóch minut”), `owner` (`{id, name, email}` właściciela), `config` (wybory z formularza) i `provisioning` (ostatnie zadanie z krokami; kroki zależą od platformy) |
| `DELETE shops/{id}/` | Usunięcie, `204`. W trakcie zakładania `409`. |
| `POST shops/{id}/resume/` | Przywrócenie sklepu zawieszonego przez plan, gdy plan ma na niego miejsce, `200` ze szczegółami. `400`: brak miejsca, `402`: brak planu, `409`: sklep nie jest zawieszony. |
| `POST shops/{id}/retry/` | Ponowienie po błędzie (wymaga potwierdzonego e-maila, a poza sklepami testowymi aktywnego planu: inaczej `402`), `202`. W innym stanie `409`. |
| `GET shops/{id}/admin-access/` | `{admin_url, sent_to}`: adres panelu sklepu i adres e-mail, na który wysłano login i hasło. Samych danych logowania API nie zwraca. Tylko dla działającego sklepu, inaczej `409`. |
| `POST shops/{id}/send-admin-access/` | Wysyła ponownie e-mail z danymi sklepu i logowaniem, `202` z `{admin_url, sent_to}`. Najwyżej 5 razy na godzinę (`429`). |
| `GET shops/check-slug/?slug=` | `{slug, available, reason}`: czy adres jest wolny i dlaczego nie |
| `GET shops/form-options/` | Wszystko do formularza: platformy (`{value, label, description, available, note}`; `available: false` z powodem w `note`, gdy plan nie pozwala teraz na sklep na tej platformie, np. Magento w planie Start), branże, języki, waluty, kraje, motywy (każdy z `platform`), zakres liczby kategorii, domena |

### Ustawienia i operacje na działającym sklepie

Wszystkie wymagają potwierdzonego e-maila. Zmiany wprowadza worker w tle (operacja), na jednym sklepie
jedna naraz. Gdy sklep nie działa albo wykonuje poprzednią operację, odpowiedź to `409` z `detail`.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/settings/` | `{values, sections, panel_name, payment_operators, server_ip, synced_at, operation, busy, options}`: ustawienia w sekcjach, sekcje, które aplikacja może zmieniać na platformie sklepu, nazwa panelu, operatorzy płatności online, których aplikacja ustawia na tej platformie (`przelewy24`, `payu`; pusta lista dla Magento), publiczny adres IP serwera sklepu (`null`, gdy nieznany), kiedy odczytano je ze sklepu, ostatnia operacja, czy sklep jest zajęty, wartości do wyboru (języki, waluty, kraje, strefy czasowe, motywy, typowe stawki VAT według kraju, formy działalności sprzedawcy do regulaminu) |
| `PATCH shops/{id}/settings/` | Dowolne sekcje i pola, np. `{"shipping": {"courier_enabled": true}}`. `202` z tym samym kształtem co `GET`, gdy coś się zmienia; `200`, gdy sklep już ma te wartości. `400` z błędami `{sekcja: {pole: [komunikat]}}`, także dla sekcji, której platforma sklepu nie ma w `sections`, i motywu innej platformy. |
| `POST shops/{id}/settings/refresh/` | Ponowny odczyt ustawień ze sklepu (np. po zmianach w panelu), `202` |
| `POST shops/{id}/documents/preview/` | Podgląd regulaminu i polityki prywatności z niezapisanymi zmianami: `{"documents": {pole: wartość}}` (pola sekcji `documents`, reszta z zapisanych ustawień). `200` z `{documents: [{key, title, blocks}]}`, `key` to `terms` albo `privacy`, `blocks` to `{type: "heading", level, text}`, `{type: "paragraph", text}` albo `{type: "list", ordered, items: [{text, items?}]}`. `400` z `{documents: {pole: [komunikat]}}`, gdy brakuje danych sprzedawcy albo sklep nie sprzedaje z Polski. Nic nie zapisuje i nie zajmuje sklepu. |
| `POST shops/{id}/reset-admin-password/` | Nowe hasło administratora, `202` z operacją. Po zakończeniu hasło przychodzi e-mailem. |
| `POST shops/{id}/remove-sample-products/` | Usunięcie produktów przykładowych, `202` z operacją; `result.removed` to ich liczba |
| `GET shops/{id}/operations/` | 20 ostatnich operacji, od najnowszej |
| `GET shops/{id}/operations/{operation_id}/` | Jedna operacja: `kind`, `status`, `changes`, `changed_fields` (etykiety zmienionych pól), `result`, `error`, `backup_created_at` (czas kopii zrobionej albo przywracanej; `null` dla innych operacji), czasy |
| `GET shops/{id}/backups/` | `{enabled, backups, manual_left, manual_per_day, keep_daily, keep_weekly, nightly_at}`: czy kopie działają (`false` bez `SHOPS_BACKUP_PASSWORD`), kopie do przywrócenia od najnowszej (`{id, kind, kind_display, created_at, size}`, rozmiar w bajtach albo `null`; `kind`: `nightly`, `manual`, `before_restore`, `before_delete`), ile kopii właściciel zrobi jeszcze dziś i ile dziennie, ile dni i tygodni zostaje po kopii, kiedy następna kopia nocna. Działa też dla zawieszonego sklepu. |
| `POST shops/{id}/backups/` | Kopia teraz, `202` z operacją `create_backup`. `409`, gdy kopie są wyłączone; `429` z `detail`, gdy dzisiejsze kopie się skończyły (nieudane się nie liczą). |
| `POST shops/{id}/backups/{backup_id}/restore/` | Przywrócenie kopii, `202` z operacją `restore_backup`; `result.before` to numer kopii stanu sprzed przywrócenia. Sklep jest nieczynny przez około minutę. Gdy przywrócenie się nie uda, sklep wraca do stanu sprzed próby, a operacja kończy się błędem z `error`. `404` dla kopii spoza listy sklepu. |

### Sprzedaż

Wymaga potwierdzonego e-maila. Worker co `SHOP_ORDERS_SYNC_MINUTES` minut kopiuje do bazy platformy zamówienia
z ostatnich 90 dni (tylko zmienione od poprzedniego odczytu), a API liczy podsumowanie z tej kopii, więc odpowiada od
razu, także gdy sklep jest wolny. Klient jest zapisany jako imię i inicjał nazwiska.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/sales/` | `{available, synced_at, refreshing, error, currency, today, last_7_days, last_30_days, previous_30_days, daily, to_handle, recent}`. Okresy to `{orders, revenue, average}` w walucie sklepu, liczone z zamówień nowych, w realizacji i zrealizowanych (bez anulowanych i nieopłaconych) według dnia złożenia w strefie platformy. `daily`: 30 dni od najstarszego, `{date, orders, revenue}`. `to_handle`: `{new, processing}`. `recent`: 10 ostatnich zamówień (bez nieopłaconych) z `external_id, number, status, status_display, total, currency, items, customer, placed_at`. Gdy kopia ma ponad 2 minuty, zleca odczyt i zwraca `refreshing: true`: aplikacja pyta ponownie co kilka sekund. `available: false` dla sklepu, który nie działa. |
| `POST shops/{id}/sales/refresh/` | Odczyt zamówień teraz (przycisk „Odśwież”), `202` z tym samym kształtem. Gdy odczyt był przed chwilą (30 s) albo już trwa, nic nowego nie zleca. |

Statusy zamówień (`status`): `new` (złożone, czeka na płatność albo potwierdzenie), `processing` (opłacone, do
wysłania), `completed`, `cancelled` (także zwrócone i nieudane), `unfinished` (płatność online niedokończona).
Każda platforma ma własne statusy, mapowane w `read_orders` i `read_order` jej provisionera.

### Zamówienia

Wymaga potwierdzonego e-maila. Lista pochodzi z tej samej kopii co sprzedaż (90 dni). Szczegóły czyta API sklepu
przy każdym otwarciu, z pełnymi danymi klienta i adresami, i niczego z nich nie zapisuje. Zmiany statusu robi sklep
przez swoje API (wysyła też swoje e-maile do klienta); notatki zespołu trzyma platforma.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/orders/` | `{available, synced_at, refreshing, error, counts, orders, has_more}`. `orders`: 30 zamówień od najnowszego, w kształcie jak `recent` w sprzedaży (także nieopłacone). Parametry: `status` (jeden ze statusów niżej), `q` (fragment numeru albo imienia klienta, `#` na początku jest pomijany), `before` (`external_id` ostatniego zamówienia z poprzedniej strony). `counts`: liczba zamówień w każdym statusie w całej kopii, bez filtrów, do przycisków statusów. Nieznany status albo `before` daje `400`. Jak sprzedaż zleca odczyt starej kopii (`refreshing`). |
| `GET shops/{id}/orders/{order_id}/` | Zamówienie odczytane teraz ze sklepu: `{external_id, number, status, status_display, currency, products_total, shipping_total, discount_total, total, payment_method, shipping_method, customer_name, email, phone, billing, shipping, lines, customer_note, placed_at, tracking_number, carrier, actions, notes}`. Kwoty brutto; produkty i dostawa przed rabatem, `total` tak, jak płaci klient. `lines`: `[{name, sku, quantity, price, total}]`. Adresy (`billing`, `shipping`, mogą być `null`): `{name, company, lines, postcode, city, country, phone}`, `country` to nazwa kraju albo kod ISO. `tracking_number` i `carrier`: przesyłka zapisana w sklepie, puste bez niej. `actions`: co można teraz zrobić, w kolejności (`mark_paid` dla nowych, `mark_shipped` dla nowych i w realizacji, `cancel` dla nowych, w realizacji i nieopłaconych; Magento nie anuluje zamówienia z fakturą). `notes`: notatki zespołu od najstarszej, `{id, text, author, created_at, can_delete}` (`author` jak w zespole albo `null` po usunięciu konta; `can_delete` dla autora i właściciela). Status w kopii przyjmuje odczytany. `404`, gdy sklep nie ma zamówienia; `409`, gdy sklep nie działa; `503` z `detail`, gdy sklep nie odpowiada, nie przyjął klucza aplikacji albo odpowiedział w nieoczekiwany sposób. |
| `POST shops/{id}/orders/{order_id}/actions/` | `{action, tracking_number?, carrier?}` → `200` z zamówieniem odczytanym po zmianie (jak wyżej). `mark_paid`: opłacone, w realizacji. `mark_shipped`: wysłane (zrealizowane), z numerem przesyłki i przewoźnikiem, gdy podane (po 60 znaków; przy innych akcjach pomijane); klient dostaje numer w wiadomości ze sklepu (PrestaShop pokazuje go tylko w szczegółach zamówienia na koncie klienta i wysyła przesyłkę przewoźnikiem z zamówienia, więc `carrier` pomija). Historia działań zapisuje przesyłkę tak, jak ją ma sklep. `cancel`: anulowane. Zmiana trafia do historii działań. `400` dla nieznanej akcji; `409` z `detail`, gdy sklep nie działa albo zamówienie nie pozwala już na tę zmianę; `404` i `503` jak przy odczycie. |
| `POST shops/{id}/orders/{order_id}/notes/` | `{text}` (do 2000 znaków) → `201` z notatką. Działa też, gdy sklep nie odpowiada. |
| `DELETE shops/{id}/orders/{order_id}/notes/{note_id}/` | `204`; `403`, gdy notatka jest innej osoby z obsługi (usuwa ją autor albo właściciel); `404`, gdy jej nie ma. |

### Produkty

Wymaga potwierdzonego e-maila; także dla obsługi. Produkty żyją tylko w sklepie: każda odpowiedź to odczyt API
sklepu w tej chwili, platforma niczego nie zapisuje. Przy sklepie, który nie działa, każdy endpoint daje `409`,
a gdy sklep nie odpowiada, nie przyjął klucza aplikacji albo odpowiedział w nieoczekiwany sposób, `503` z `detail`.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/products/` | `{currency, products, has_more}`, po 30, od najnowszego, także ukryte. Produkt: `{external_id, name, sku, price, regular_price, stock, in_stock, visible, image, has_variants}`. `price`: brutto tak, jak płaci klient (w PrestaShop liczy ją sklep; w WooCommerce i Magento cena wpisana w sklepie, brutto przy ustawieniu platformy), z wariantami najniższa, `null` bez ceny. `regular_price`: cena przed promocją, tylko gdy trwa. `stock`: sztuki, `null`, gdy sklep ich nie liczy (WooCommerce bez zarządzania stanem). `in_stock`: można kupić. `visible`: klienci go widzą. `image`: adres głównego zdjęcia albo pusty. `has_variants`: warianty albo zestaw, z własnymi stanami (zmiana w panelu). Parametry: `q` (fragment nazwy; w Magento także SKU), `stock=out_of_stock` (tylko braki), `page` (od 1, do 1000). Zły filtr albo strona daje `400`. |
| `GET shops/{id}/products/{product_id}/` | Produkt jak wyżej oraz `currency`, `categories` (nazwy, bez kategorii głównej) i `url` (strona produktu w sklepie, pusta dla ukrytego). `404`, gdy sklep go nie ma. |
| `POST shops/{id}/products/{product_id}/stock/` | `{quantity}` (0–999999) → `200` z produktem odczytanym po zmianie. Sklep zaczyna liczyć sztuki, jeśli nie liczył; przy 0 przestaje sprzedawać produkt. Zmiana trafia do historii działań. `409` z `detail` dla produktu z wariantami; `400` dla złej liczby. |

### Lista startowa

Wymaga potwierdzonego e-maila. Kroki, które nowy sklep ma zrobić przed sprzedażą. Każdy odhacza się sam, z tego, co
platforma wie o sklepie; nie ma ręcznych ptaszków.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/checklist/` | `{available, hidden, steps, products, sample_products, counted_at, refreshing}`. `steps`: `[{key, done}]` w kolejności do pokazania, tylko kroki, które dotyczą sklepu. `products` i `sample_products`: własne i przykładowe produkty policzone w sklepie (także szkice), `null` przed pierwszym liczeniem. Gdy krok z produktami jest otwarty, a ostatnie liczenie było ponad 2 minuty temu, zleca liczenie; bez zamówień zleca też odczyt zamówień (jak podsumowanie sprzedaży). `refreshing: true`, gdy trwa liczenie, odczyt zamówień albo operacja na sklepie: aplikacja pyta ponownie co kilka sekund. `available: false` dla sklepu, który nie działa, i dla ukrytej listy (wtedy `steps` jest puste). |
| `PATCH shops/{id}/checklist/` | `{hidden}`: ukrywa listę albo pokazuje ją z powrotem; odpowiedź jak w `GET` |

Kroki (`key`) i kiedy są zrobione:

| Krok | Zrobiony, gdy | Dotyczy |
|---|---|---|
| `payments` | jest włączony przelew, płatność przy odbiorze, Przelewy24 albo PayU | platform z sekcją `payments` |
| `shipping` | jest włączony kurier, darmowa dostawa albo odbiór osobisty | platform z sekcją `shipping` (nie PrestaShop) |
| `documents` | aplikacja prowadzi regulamin i politykę prywatności, a dokumenty są już w sklepie | platform z sekcją `documents` (wszystkich) |
| `products` | w sklepie jest co najmniej jeden własny produkt | każdego sklepu |
| `sample_products` | w sklepie nie zostały produkty przykładowe | sklepu założonego z produktami przykładowymi |
| `notifications` | właściciel ma telefon zarejestrowany do powiadomień | każdego sklepu |
| `test_order` | w kopii zamówień jest jakiekolwiek zamówienie, także anulowane | każdego sklepu |

Sekcje i pola ustawień (pełny opis w `/api/docs/` i w [shop_settings.py](../backend/shops/shop_settings.py)):

| Sekcja | Pola |
|---|---|
| `general` | `name`, `description`, `contact_email` |
| `availability` | `is_open` (wyłączony: strona „wkrótce otwarcie”) |
| `shopping` | `guest_checkout`, `signup_at_checkout`, `reviews`, `manage_stock`, `low_stock_threshold` |
| `payments` | `bank_transfer_enabled`, `bank_account_name`, `bank_account_number` (sprawdzany jak IBAN), `bank_name`, `cash_on_delivery_enabled`; Przelewy24: `przelewy24_enabled`, `przelewy24_sandbox`, `przelewy24_merchant_id`, `przelewy24_crc_key`, `przelewy24_api_key`, `przelewy24_keys_saved`; PayU: `payu_enabled`, `payu_sandbox`, `payu_pos_id`, `payu_client_id`, `payu_md5_key`, `payu_client_secret`, `payu_keys_saved` |
| `shipping` | `courier_enabled`, `courier_cost`, `free_shipping_enabled`, `free_shipping_min_amount`, `local_pickup_enabled` |
| `taxes` | `enabled`, `prices_include_tax`, `standard_rate` |
| `region` | `language`, `currency`, `country`, `timezone` |
| `appearance` | `theme` (slug motywu) |
| `documents` | `managed`, dane sprzedawcy: `seller_name`, `register` (`ceidg`, `krs`, `unregistered`), `street`, `postal_code`, `city`, `tax_id`, `regon`, `krs`, `phone`; `return_days` (14–365), `free_returns`, `dispatch_days` (1–30); tylko do odczytu: `terms_url`, `privacy_url`, `version` |

Kwoty i stawki są tekstem z dwoma miejscami po przecinku (`"15.00"`). Zmiana kraju bez podania strefy czasowej
i stawki VAT ustawia te typowe dla nowego kraju. Reguły obejmujące kilka pól: przelew wymaga odbiorcy i numeru konta,
a klient musi móc kupić bez konta albo założyć je przy zamówieniu.

Regulamin i polityka prywatności (sekcja `documents`):

- Dokumenty powstają z naszych wzorów ([templates/shops/documents/](../backend/shops/templates/shops/documents/))
  i ustawień sklepu: dane sprzedawcy i zwroty z tej sekcji, a nazwa, e-mail, opinie, płatności, dostawy i waluta
  z pozostałych. Worker publikuje je jako strony sklepu i zapisuje ich adresy w `terms_url` i `privacy_url`.
- `managed: true` publikuje dokumenty od razu. Potem każda zmiana sekcji `general`, `shopping`, `payments`,
  `shipping`, `region` albo `documents` publikuje je jeszcze raz, w tej samej operacji. Nieudana publikacja to
  nieudana operacja, więc zmiana nie jest zapisana. `managed: false` tylko zatrzymuje aktualizacje: strony zostają
  w sklepie.
- Przy `managed: true` wymagane są `seller_name`, `street`, `postal_code`, `city`, a dla `ceidg` i `krs` także
  `tax_id`; dla `krs` też `krs`. Brak daje `400` „Potrzebne do regulaminu.” Sprawdzamy format NIP (suma kontrolna),
  REGON (9 albo 14 cyfr), KRS (10 cyfr), kodu pocztowego i telefonu.
- Wzory są dla sklepów sprzedających z Polski: `managed: true` w sklepie z innym krajem i zmiana kraju sklepu, który
  ma dokumenty z aplikacji, dają `400`.
- Dane sprzedawcy na start bierzemy z danych do faktur właściciela (NIP tylko polskiej firmy).
- Nowa wersja wzorów: operacja `publish_documents` (bez `changes`), zlecana poleceniem `publish_shop_documents`
  ([obsługa](obsluga.md)).

Płatności online (Przelewy24, PayU; tylko operatorzy z `payment_operators`):

- Klucze (`przelewy24_crc_key`, `przelewy24_api_key`, `payu_md5_key`, `payu_client_secret`) są tylko do zapisu.
  Trafiają do sklepu i nigdzie ich nie trzymamy. W `GET` są tylko `*_keys_saved`: czy sklep ma klucze. Puste pole
  klucza zostawia ten, który ma sklep. Do czasu, aż worker wpisze klucze do sklepu, czekają zaszyfrowane
  w operacji, a potem są usuwane, także po nieudanej zmianie. W `changes` operacji klucz jest zastąpiony przez
  `"••••••••"`.
- Włączenie operatora wymaga jego identyfikatorów i kluczy. Bez kluczy w sklepie i po zmianie trybu
  (`*_sandbox`) klucze trzeba podać, bo klucze testowe i produkcyjne są różne. Reguły sprawdzamy tylko dla operatora,
  którego pola są w zmianie, więc operator włączony w panelu sklepu bez kluczy nie blokuje innych zmian.
- Format: identyfikatory to same cyfry. Klucz CRC Przelewy24 ma 16 znaków szesnastkowych, pozostałe klucze po 32.
  Spacje są usuwane, a litery zamieniane na małe.
- Pierwsze włączenie instaluje w sklepie oficjalną wtyczkę albo moduł operatora (kilkadziesiąt sekund).
  Wyłączenie wyłącza tylko płatność: wtyczka i jej ustawienia zostają w sklepie.
- Operator na platformie spoza `payment_operators` (Magento): `400` przy `{operator}_enabled`, „Płatności … nie są
  jeszcze dostępne na platformie tego sklepu.”

Pola formularza `POST shops/`:

| Pole | Wymagane | Opis |
|---|---|---|
| `name` | tak | 2–100 znaków |
| `slug` | tak | Adres: 3–30 znaków, `a-z`, `0-9`, `-` |
| `industry` | tak | Wartość z `form-options.industries` |
| `platform` | nie | `woocommerce` albo `prestashop`; domyślnie platforma motywu. Motyw innej platformy daje `400` przy `template` |
| `template` | tak | `slug` motywu z `form-options.templates` |
| `category_count` | nie | 1–20, domyślnie z `form-options.category_count.default` |
| `language`, `currency`, `country` | nie | Domyślnie `pl_PL`, `PLN`, `PL` |
| `contact_email` | nie | Domyślnie e-mail właściciela konta |
| `description` | nie | Do 500 znaków, trafia do opisu witryny |
| `include_sample_products` | nie | Domyślnie `true` |

### Historia działań

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/history/` | Tylko właściciel, z potwierdzonym e-mailem. `{events, has_more}`, od najnowszych, po 30. Wpis: `{id, kind, title, detail, actor, actor_role, status, error, created_at}`. `title` i `detail` to gotowy tekst (np. „Zmiana ustawień”, „Waluta, Język”; „Wysłanie zamówienia”, „Nr #7, przesyłka 6200123 (InPost)”; „Zmiana stanu produktu”, „Kawa: 3 → 20 szt.”). `actor`: `{id, name, email}` albo `null`; `actor_role`: `owner`, `staff` (także była obsługa), `system` (platforma, np. zawieszenie przez plan) albo `deleted` (usunięte konto). `status` i `error`: stan zmiany w sklepie (`queued`, `running`, `succeeded`, `failed`), dla innych wpisów `null` i puste. Starsze: `?before=<id ostatniego wpisu>`. |

### Zespół

Tylko dla właściciela, z potwierdzonym e-mailem. Limit osób z obsługi to `max_staff` planu właściciela, osobno
w każdym sklepie i bez właściciela; liczą się do niego też ważne zaproszenia. Bez planu nie można nikogo zaprosić.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/team/` | `{owner, members, invitations, limit, used}`. `owner`: `{id, name, email}`. `members`: `{id, name, email, joined_at}` (`id` osoby). `invitations`: `{id, email, created_at, expires_at, expired}`, także przeterminowane (do ponownego wysłania). `limit`: `null` bez limitu. `used`: osoby i ważne zaproszenia. |
| `POST shops/{id}/team/invitations/` | `{email}` → `201` z zaproszeniem i e-mail z linkiem do aplikacji (`APP_URL`: logowanie albo rejestracja z wpisanym adresem). Zaproszenie tego samego adresu odnawia termin (7 dni) i wysyła e-mail ponownie. `400` z `{email: [...]}` dla adresu właściciela albo osoby z zespołu, `409` z `detail`, gdy plan nie ma miejsca. Najwyżej 30 na godzinę. |
| `DELETE shops/{id}/team/invitations/{invitation_id}/` | Cofnięcie zaproszenia, `204`; `404`, gdy go nie ma |
| `DELETE shops/{id}/team/members/{user_id}/` | Usunięcie osoby z zespołu, `204`; `404`, gdy jej nie ma |
| `POST shops/{id}/leave/` | Dla obsługi: opuszczenie zespołu, `204`. Właściciel dostaje `409`. |

## Zaproszenia: `/api/invitations/`

Zaproszenia do zespołów cudzych sklepów na potwierdzony adres zalogowanej osoby (konto bez potwierdzonego e-maila
nie widzi żadnych). Przeterminowane i do usuniętych sklepów znikają z listy.

| Metoda i ścieżka | Opis |
|---|---|
| `GET invitations/` | `[{id, shop: {id, name, url, platform, platform_display}, invited_by: {id, name, email} \| null, created_at, expires_at}]` |
| `POST invitations/{id}/accept/` | Dołączenie do zespołu, `200` ze sklepem jak na liście (`role: staff`). Zaproszenie znika. `409`, gdy zespół jest już pełny (plan właściciela mógł się zmienić). |
| `POST invitations/{id}/decline/` | Odrzucenie, `204` |

## Powiadomienia push: `/api/push/`

Wymagają potwierdzonego e-maila. Wysyłka idzie przez usługę Expo Push w tle; aplikacja tylko zgłasza telefon
i wybiera tematy.

| Metoda i ścieżka | Opis |
|---|---|
| `POST push/devices/` | `{token, platform, name}`: token Expo (`ExponentPushToken[…]`), `ios` albo `android`, model telefonu. `201` dla nowego telefonu, `200` przy kolejnym zgłoszeniu. Telefon zalogowany na inne konto przechodzi do bieżącego. Zły format tokenu: `400`. |
| `POST push/devices/forget/` | `{token}`: przy wylogowaniu telefon przestaje dostawać powiadomienia konta, `204` (także gdy go nie było) |
| `GET push/preferences/` | `{new_orders, shops, billing, devices}`: tematy (domyślnie wszystkie włączone) i telefony `{name, platform, platform_display, last_seen_at}`, bez tokenów |
| `PATCH push/preferences/` | Dowolne z `new_orders`, `shops`, `billing`; zwraca to samo co `GET` |

Tematy: `new_orders` (nowe zamówienie w sklepie), `shops` (sklep gotowy, błąd zakładania), `billing` (nieudana opłata,
koniec planu). Powiadomienie ma w `data.url` ścieżkę ekranu aplikacji, który otwiera, np. `/shops/7/orders/15` (nowe zamówienie; kilka naraz otwiera `/shops/7/orders`).
Wylogowanie ze wszystkich urządzeń, zmiana i reset hasła oraz usunięcie konta usuwają wszystkie telefony konta.

## Płatności: `/api/billing/`

Plany, dane do faktury, płatność kartą, anulowanie i powiadomienia od operatora: [platnosci.md](platnosci.md#api).
`GET auth/me/` zwraca też `plan` (nazwa albo `null`), `shop_limit` (0 bez planu), `magento_shop_limit`
(ile z tych sklepów może działać na Magento; 0 bez planu albo w planie bez Magento) i `can_create_shops`.

## Kontakt: `/api/contact/`

| Metoda i ścieżka | Logowanie | Opis |
|---|---|---|
| `POST contact/` | nie | `{name, email, topic, message}` → `201`. `topic`: `question`, `shop_problem`, `billing`, `other`. Limit: 5 wiadomości na godzinę. |

## Inne

| Metoda i ścieżka | Logowanie | Opis |
|---|---|---|
| `GET health/` | nie | `{"status": "OK"}`: czy API działa |
| `GET schema/`, `GET docs/` | nie | Schemat OpenAPI i Swagger |
| `GET /media/avatars/<nazwa>.webp` | nie | Plik zdjęcia profilowego (poza `/api/`). Każde wgranie dostaje nową losową nazwę, więc odpowiedź ma `Cache-Control: immutable`. Pliki leżą w `MEDIA_ROOT`, w Dockerze na wolumenie `media`. |

## Dodawanie endpointu

1. Serializer z opisem pól, widok wołający funkcję z `services.py`.
2. `@extend_schema` przy widoku, jeśli drf-spectacular nie wywnioskuje typów sam (np. `APIView` albo akcje).
3. Test w `tests/` danej aplikacji.
4. `python manage.py spectacular --validate --fail-on-warn` bez ostrzeżeń.
5. Wpis w tabeli powyżej.
