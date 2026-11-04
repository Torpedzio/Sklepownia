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
| `GET shops/{id}/admin-access/` | `{admin_url, username, password}` do panelu WordPressa. Tylko dla działającego sklepu, inaczej `409`. |
| `GET shops/check-slug/?slug=` | `{slug, available, reason}`: czy adres jest wolny i dlaczego nie |
| `GET shops/form-options/` | Wszystko do formularza: branże, języki, waluty, kraje, motywy, zakres liczby kategorii, domena |

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
