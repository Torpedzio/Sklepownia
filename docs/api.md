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
| `POST register/` | nie | `{email, password}` → `201 {user, tokens}`. Wysyła kod potwierdzający. |
| `POST login/` | nie | `{email, password}` → `{access, refresh}`. Wielkość liter w e-mailu nie ma znaczenia. |
| `POST refresh/` | nie | `{refresh}` → `{access, refresh}` |
| `POST logout/` | tak | `{refresh}` → `205`. Unieważnia token odświeżania. |
| `POST logout-everywhere/` | tak | `205`. Unieważnia wszystkie tokeny odświeżania konta: wylogowanie na każdym urządzeniu. |
| `POST change-password/` | tak | `{current_password, new_password}` → `{access, refresh}`. Inne urządzenia są wylogowane, to dostaje nowe tokeny, a właściciel e-mail o zmianie. `400` przy złym obecnym albo słabym nowym haśle. |
| `POST password-reset/` | nie | `{email}` → `204`. Wysyła kod do ustawienia nowego hasła (ważny 15 min). Odpowiedź jest taka sama dla adresu bez konta i dla ponownej prośby w ciągu 60 s (wtedy nic nie wychodzi), żeby nie dało się sprawdzać, kto ma konto. |
| `POST password-reset/confirm/` | nie | `{email, code, new_password}` → `{access, refresh}`: nowe hasło i od razu zalogowanie. Inne urządzenia są wylogowane, właściciel dostaje e-mail o zmianie, a niepotwierdzony adres staje się potwierdzony (kod dowodzi dostępu do skrzynki). `400` z `{code: [...]}` przy złym, wygasłym albo zablokowanym kodzie (5 prób; dla nieznanego adresu ten sam komunikat) albo `{new_password: [...]}` przy słabym haśle, po którym kod dalej działa. |
| `POST delete-account/` | tak | `{password}` → `204`. Usuwa konto ze wszystkimi sklepami: plan kończy się od razu (bez zwrotu za resztę okresu), karta, dane do faktury i zdjęcie znikają, a konto zostaje zanonimizowane i wylogowane wszędzie. Opłacone płatności zostają dla przepisów podatkowych. Na dawny adres idzie potwierdzenie z listą usuniętych sklepów, a adres jest od razu wolny. `400` z `{password: [...]}` przy złym haśle; `409 {detail}`, gdy sklep jest w kolejce albo właśnie zakładany, albo dla konta administratora (to usuwa się w panelu). |
| `GET me/` | tak | Dane konta: `id, email, first_name, last_name, is_email_verified, date_joined, shop_limit, plan, can_create_shops, avatar_url` |
| `PATCH me/` | tak | Zmiana `first_name`, `last_name` |
| `PUT avatar/` | tak | `multipart/form-data` z polem `avatar` (JPG, PNG, WebP albo GIF do 10 MB) → dane konta. Serwer przycina zdjęcie do kwadratu 512×512, zapisuje jako WebP bez metadanych (EXIF, GPS) i usuwa poprzednie. `400` z `{avatar: [...]}`, gdy plik nie jest obsługiwanym zdjęciem. |
| `DELETE avatar/` | tak | Usuwa zdjęcie profilowe → dane konta z `avatar_url: null`. |
| `POST verify-email/` | tak | `{code}` (6 cyfr) → dane konta z `is_email_verified: true` |
| `POST resend-verification/` | tak | `204`. Nowy kod najwcześniej po 60 s, inaczej `429`. |

Limity zapytań: logowanie, rejestracja i ustawianie nowego hasła 10 na minutę, potwierdzanie e-maila 10 na godzinę, prośby o kod do nowego hasła 5 na godzinę z jednego adresu IP, zmiana zdjęcia profilowego 30 na godzinę.

## Sklepy: `/api/shops/`

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/` | Sklepy użytkownika (bez usuniętych): `id, name, slug, url, status, status_display, platform, platform_display, is_test, created_at`. `platform`: `woocommerce` albo `prestashop`. `is_test`: sklep sprzed płatnych planów |
| `POST shops/` | Założenie sklepu (wymaga potwierdzonego e-maila i aktywnego planu). `201` ze szczegółami sklepu. `402` bez planu, `400` przy zajętym adresie albo osiągniętym limicie planu (sklepy testowe się nie liczą); limit sklepów Magento daje błąd pola `platform`. |
| `GET shops/{id}/` | Szczegóły: pola z listy plus `panel_name` (np. „panel PrestaShop”), `setup_time` (ile trwa zakładanie, np. „około dwóch minut”), `config` (wybory z formularza) i `provisioning` (ostatnie zadanie z krokami; kroki zależą od platformy) |
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
| `GET shops/{id}/settings/` | `{values, sections, panel_name, synced_at, operation, busy, options}`: ustawienia w sekcjach, sekcje, które aplikacja może zmieniać na platformie sklepu, nazwa panelu, kiedy odczytano je ze sklepu, ostatnia operacja, czy sklep jest zajęty, wartości do wyboru (języki, waluty, kraje, strefy czasowe, motywy, typowe stawki VAT według kraju) |
| `PATCH shops/{id}/settings/` | Dowolne sekcje i pola, np. `{"shipping": {"courier_enabled": true}}`. `202` z tym samym kształtem co `GET`, gdy coś się zmienia; `200`, gdy sklep już ma te wartości. `400` z błędami `{sekcja: {pole: [komunikat]}}`, także dla sekcji, której platforma sklepu nie ma w `sections`, i motywu innej platformy. |
| `POST shops/{id}/settings/refresh/` | Ponowny odczyt ustawień ze sklepu (np. po zmianach w panelu), `202` |
| `POST shops/{id}/reset-admin-password/` | Nowe hasło administratora, `202` z operacją. Po zakończeniu hasło przychodzi e-mailem. |
| `POST shops/{id}/remove-sample-products/` | Usunięcie produktów przykładowych, `202` z operacją; `result.removed` to ich liczba |
| `GET shops/{id}/operations/` | 20 ostatnich operacji, od najnowszej |
| `GET shops/{id}/operations/{operation_id}/` | Jedna operacja: `kind`, `status`, `changes`, `changed_fields` (etykiety zmienionych pól), `result`, `error`, czasy |

### Sprzedaż

Wymaga potwierdzonego e-maila. Worker co `SHOP_ORDERS_SYNC_MINUTES` minut kopiuje do bazy platformy zamówienia
z ostatnich 90 dni (tylko zmienione od poprzedniego odczytu), a API liczy podsumowanie z tej kopii, więc odpowiada od
razu, także gdy sklep jest wolny. Klient jest zapisany jako imię i inicjał nazwiska.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/sales/` | `{available, synced_at, refreshing, error, currency, today, last_7_days, last_30_days, previous_30_days, daily, to_handle, recent}`. Okresy to `{orders, revenue, average}` w walucie sklepu, liczone z zamówień nowych, w realizacji i zrealizowanych (bez anulowanych i nieopłaconych) według dnia złożenia w strefie platformy. `daily`: 30 dni od najstarszego, `{date, orders, revenue}`. `to_handle`: `{new, processing}`. `recent`: 10 ostatnich zamówień (bez nieopłaconych) z `number, status, status_display, total, currency, items, customer, placed_at`. Gdy kopia ma ponad 2 minuty, zleca odczyt i zwraca `refreshing: true`: aplikacja pyta ponownie co kilka sekund. `available: false` dla sklepu, który nie działa. |
| `POST shops/{id}/sales/refresh/` | Odczyt zamówień teraz (przycisk „Odśwież”), `202` z tym samym kształtem. Gdy odczyt był przed chwilą (30 s) albo już trwa, nic nowego nie zleca. |

Statusy zamówień (`status`): `new` (złożone, czeka na płatność albo potwierdzenie), `processing` (opłacone, do
wysłania), `completed`, `cancelled` (także zwrócone i nieudane), `unfinished` (płatność online niedokończona).
Każda platforma ma własne statusy, mapowane w `read_orders` jej provisionera.

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
| `payments` | jest włączony przelew albo płatność przy odbiorze | platform z sekcją `payments` |
| `shipping` | jest włączony kurier, darmowa dostawa albo odbiór osobisty | platform z sekcją `shipping` (nie PrestaShop) |
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
| `payments` | `bank_transfer_enabled`, `bank_account_name`, `bank_account_number` (sprawdzany jak IBAN), `bank_name`, `cash_on_delivery_enabled` |
| `shipping` | `courier_enabled`, `courier_cost`, `free_shipping_enabled`, `free_shipping_min_amount`, `local_pickup_enabled` |
| `taxes` | `enabled`, `prices_include_tax`, `standard_rate` |
| `region` | `language`, `currency`, `country`, `timezone` |
| `appearance` | `theme` (slug motywu) |

Kwoty i stawki są tekstem z dwoma miejscami po przecinku (`"15.00"`). Zmiana kraju bez podania strefy czasowej
i stawki VAT ustawia te typowe dla nowego kraju. Reguły obejmujące kilka pól: przelew wymaga odbiorcy i numeru konta,
a klient musi móc kupić bez konta albo założyć je przy zamówieniu.

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
koniec planu). Powiadomienie ma w `data.url` ścieżkę ekranu aplikacji, który otwiera, np. `/shops/7/sales`.
Wylogowanie ze wszystkich urządzeń, zmiana i reset hasła oraz usunięcie konta usuwają wszystkie telefony konta.

## Płatności: `/api/billing/`

Plany, dane do faktury, płatność kartą, anulowanie i powiadomienia od operatora: [platnosci.md](platnosci.md#api).
`GET auth/me/` zwraca też `plan` (nazwa albo `null`), `shop_limit` (0 bez planu) i `can_create_shops`.

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
