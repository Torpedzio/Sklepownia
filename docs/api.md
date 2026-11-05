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
| `GET me/` | tak | Dane konta: `id, email, first_name, last_name, is_email_verified, date_joined, shop_limit` |
| `PATCH me/` | tak | Zmiana `first_name`, `last_name` |
| `POST verify-email/` | tak | `{code}` (6 cyfr) → dane konta z `is_email_verified: true` |
| `POST resend-verification/` | tak | `204`. Nowy kod najwcześniej po 60 s, inaczej `429`. |

Limity zapytań: logowanie i rejestracja 10 na minutę, potwierdzanie e-maila 10 na godzinę.

## Sklepy: `/api/shops/`

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/` | Sklepy użytkownika (bez usuniętych): `id, name, slug, url, status, status_display, created_at` |
| `POST shops/` | Założenie sklepu (wymaga potwierdzonego e-maila). `201` ze szczegółami sklepu. `400` przy zajętym adresie albo osiągniętym limicie. |
| `GET shops/{id}/` | Szczegóły: pola z listy plus `config` (wybory z formularza) i `provisioning` (ostatnie zadanie z krokami) |
| `DELETE shops/{id}/` | Usunięcie, `204`. W trakcie zakładania `409`. |
| `POST shops/{id}/retry/` | Ponowienie po błędzie (wymaga potwierdzonego e-maila), `202`. W innym stanie `409`. |
| `GET shops/{id}/admin-access/` | `{admin_url, sent_to}`: adres panelu WordPressa i adres e-mail, na który wysłano login i hasło. Samych danych logowania API nie zwraca. Tylko dla działającego sklepu, inaczej `409`. |
| `POST shops/{id}/send-admin-access/` | Wysyła ponownie e-mail z danymi sklepu i logowaniem, `202` z `{admin_url, sent_to}`. Najwyżej 5 razy na godzinę (`429`). |
| `GET shops/check-slug/?slug=` | `{slug, available, reason}`: czy adres jest wolny i dlaczego nie |
| `GET shops/form-options/` | Wszystko do formularza: branże, języki, waluty, kraje, motywy, zakres liczby kategorii, domena |

### Ustawienia i operacje na działającym sklepie

Wszystkie wymagają potwierdzonego e-maila. Zmiany wprowadza worker w tle (operacja), na jednym sklepie
jedna naraz. Gdy sklep nie działa albo wykonuje poprzednią operację, odpowiedź to `409` z `detail`.

| Metoda i ścieżka | Opis |
|---|---|
| `GET shops/{id}/settings/` | `{values, synced_at, operation, busy, options}`: ustawienia w sekcjach, kiedy odczytano je ze sklepu, ostatnia operacja, czy sklep jest zajęty, wartości do wyboru (języki, waluty, kraje, strefy czasowe, motywy, typowe stawki VAT według kraju) |
| `PATCH shops/{id}/settings/` | Dowolne sekcje i pola, np. `{"shipping": {"courier_enabled": true}}`. `202` z tym samym kształtem co `GET`, gdy coś się zmienia; `200`, gdy sklep już ma te wartości. `400` z błędami `{sekcja: {pole: [komunikat]}}`. |
| `POST shops/{id}/settings/refresh/` | Ponowny odczyt ustawień ze sklepu (np. po zmianach w wp-admin), `202` |
| `POST shops/{id}/reset-admin-password/` | Nowe hasło administratora, `202` z operacją. Po zakończeniu hasło przychodzi e-mailem. |
| `POST shops/{id}/remove-sample-products/` | Usunięcie produktów przykładowych, `202` z operacją; `result.removed` to ich liczba |
| `GET shops/{id}/operations/` | 20 ostatnich operacji, od najnowszej |
| `GET shops/{id}/operations/{operation_id}/` | Jedna operacja: `kind`, `status`, `changes`, `changed_fields` (etykiety zmienionych pól), `result`, `error`, czasy |

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
| `template` | tak | `slug` motywu z `form-options.templates` |
| `category_count` | nie | 1–20, domyślnie z `form-options.category_count.default` |
| `language`, `currency`, `country` | nie | Domyślnie `pl_PL`, `PLN`, `PL` |
| `contact_email` | nie | Domyślnie e-mail właściciela konta |
| `description` | nie | Do 500 znaków, trafia do opisu witryny |
| `include_sample_products` | nie | Domyślnie `true` |

## Kontakt: `/api/contact/`

| Metoda i ścieżka | Logowanie | Opis |
|---|---|---|
| `POST contact/` | nie | `{name, email, topic, message}` → `201`. `topic`: `question`, `shop_problem`, `billing`, `other`. Limit: 5 wiadomości na godzinę. |

## Inne

| Metoda i ścieżka | Logowanie | Opis |
|---|---|---|
| `GET health/` | nie | `{"status": "OK"}`: czy API działa |
| `GET schema/`, `GET docs/` | nie | Schemat OpenAPI i Swagger |

## Dodawanie endpointu

1. Serializer z opisem pól, widok wołający funkcję z `services.py`.
2. `@extend_schema` przy widoku, jeśli drf-spectacular nie wywnioskuje typów sam (np. `APIView` albo akcje).
3. Test w `tests/` danej aplikacji.
4. `python manage.py spectacular --validate --fail-on-warn` bez ostrzeżeń.
5. Wpis w tabeli powyżej.
