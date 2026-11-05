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
                                   │                                          (WordPress) │
                                   │                       MariaDB shops-db ◀─┘           │
                                   └──────────────────────────────────────────────────────┘
```

| Składnik | Rola | Gdzie |
|---|---|---|
| Aplikacja | Strony publiczne, konto, lista sklepów, formularz, postęp zakładania, porady | [mobile/](../mobile/) |
| Backend | REST API, uwierzytelnianie JWT, logika sklepów, panel admina Django | [backend/](../backend/) |
| PostgreSQL | Konta, sklepy, konfiguracja, zaszyfrowane hasła sklepów, postęp zakładania | `db` w [docker-compose.yml](../docker-compose.yml) |
| Redis | Kolejka zadań Celery | `redis` |
| Worker Celery | Wykonuje długie zadania: zakładanie i usuwanie sklepów, wysyłkę e-maili | `worker` |
| Mailpit | Lokalny serwer SMTP: przyjmuje całą pocztę i pokazuje ją w przeglądarce. Na produkcji zastępuje go dostawca poczty. | `mail` |
| Traefik | Kieruje ruch do kontenera sklepu po nazwie hosta | `shops-proxy` w [infra/shops/](../infra/shops/) |
| MariaDB | Jedna instancja, osobna baza i użytkownik dla każdego sklepu | `shops-db` |
| Kontener sklepu | WordPress + WooCommerce + motyw, jeden na sklep | `shop-<id>`, obraz `shops/wordpress:7.1` |

Backend i worker to ten sam kod. Tylko worker ma dostęp do socketu Dockera, bo tylko on zakłada kontenery.
Proces API nie dotyka Dockera (klient Dockera jest tworzony leniwie, dopiero przy pierwszym kroku).

## Przebieg zakładania sklepu

1. Aplikacja wysyła formularz: `POST /api/shops/`.
2. Backend w jednej transakcji ([services.create_shop](../backend/shops/services.py)):
   - blokuje wiersz użytkownika i sprawdza limit sklepów (`SHOPS_MAX_PER_USER`),
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

Kroki zakładania i ich techniczny opis: [infra/shops/README.md](../infra/shops/README.md#kroki-i-czasy).

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

## Stany sklepu

| Stan | Znaczenie | Może przejść do |
|---|---|---|
| `pending` | Czeka w kolejce na workera | `provisioning`, `failed`, `deleted` |
| `provisioning` | Worker wykonuje kroki | `active`, `failed` |
| `active` | Sklep działa | `suspended`, `deleted` |
| `failed` | Zakładanie przerwane błędem | `pending` (ponowienie), `deleted` |
| `suspended` | Zawieszony | `active`, `deleted` |
| `deleted` | Usunięty (wiersz zostaje w bazie) | — |

Dozwolone przejścia są w `Shop.ALLOWED_TRANSITIONS` ([models.py](../backend/shops/models.py)).
Niedozwolone przejście rzuca `InvalidTransition`; API zamienia je na `409 Conflict`
(np. usunięcie sklepu w trakcie zakładania). Stan `suspended` jest przewidziany w modelu, ale nic go jeszcze nie ustawia.

## Provisionery

Sposób zakładania sklepów wybiera zmienna `SHOP_PROVISIONER`:

| Provisioner | Do czego |
|---|---|
| `shops.provisioning.fake.FakeProvisioner` | Symulacja bez infrastruktury: każdy krok czeka `FAKE_PROVISIONER_STEP_DELAY` sekund, opcjonalny błąd w kroku `FAKE_PROVISIONER_FAIL_AT_STEP`. Używany w testach. |
| `shops.provisioning.docker_provisioner.DockerProvisioner` | Prawdziwe sklepy na serwerze z [infra/shops/](../infra/shops/), polecenia przez Docker API i WP-CLI w kontenerze sklepu. |

Oba dziedziczą po `BaseProvisioner`, który definiuje listę kroków (`STEPS`) oraz `cleanup`, `teardown` i `update_address`,
a dla działających sklepów `read_settings`, `apply_settings`, `reset_admin_password` i `remove_sample_products`.
`FakeProvisioner` trzyma ustawienia tylko w bazie platformy, a błąd można wywołać, podając w
`FAKE_PROVISIONER_FAIL_AT_STEP` nazwę metody (np. `apply_settings`).

## Adresy sklepów

Adres sklepu to `<scheme>://<slug>.<SHOPS_BASE_DOMAIN>[:port]`, liczony na bieżąco z ustawień
(`Shop.url`, `Shop.admin_url`). Ten sam adres jest zapisany w bazie WordPressa i w regule Traefika kontenera,
więc po zmianie domeny trzeba przenieść istniejące sklepy poleceniem `update_shop_addresses`
([docs/obsluga.md](obsluga.md#zmiana-sieci-lub-adresu-ip)).

## Bezpieczeństwo

- Hasła sklepów (baza, administrator WordPressa, hasło API) są zaszyfrowane w bazie kluczem Fernet `FIELD_ENCRYPTION_KEY`
  (`EncryptedTextField`). Każde hasło jest zapisywane, zanim zostanie użyte, żeby ponowiona próba go nie zgubiła.
- Login i hasło administratora sklepu nie wychodzą przez API. Trafiają tylko e-mailem na adres konta właściciela:
  po założeniu sklepu, po zmianie hasła i na prośbę (`send-admin-access`, najwyżej 5 razy na godzinę).
  Aplikacja pokazuje tylko adres panelu i adres, na który wysłano dane.
- Użytkownik widzi tylko swoje sklepy (`ShopViewSet.get_queryset`). Zakładanie i ponawianie wymaga potwierdzonego e-maila.
- Komunikaty błędów kroków pokazywane użytkownikowi pochodzą tylko z `ProvisioningError`; inne wyjątki
  (mogące zawierać hasła lub nazwy hostów) zastępuje ogólny komunikat, a szczegóły trafiają do logów workera.
- Endpointy logowania, weryfikacji e-maila i formularza kontaktowego mają limity zapytań (throttling).
- Worker ma dostęp do socketu Dockera, czyli w praktyce uprawnienia roota na serwerze sklepów.
  Na produkcji trzeba to ograniczyć: [docs/ograniczenia-i-plan.md](ograniczenia-i-plan.md).
