# Płatności i plany

Sklepy zakłada się w ramach płatnego planu. Właściciel wybiera plan, podaje dane do faktury
(osoba prywatna albo firma z NIP) i płaci kartą u operatora płatności. Kolejne okresy platforma
opłaca sama z zapisanej karty. Kod jest w [backend/billing/](../backend/billing/).

Sklepy założone przed wprowadzeniem płatności są **testowe** (`Shop.is_test`): działają bez planu
i nie liczą się do jego limitu.

## Jak to działa

```
aplikacja ──PUT /billing/profile/──▶ backend            (dane do faktury)
aplikacja ──POST /billing/checkout/─▶ backend ──▶ Tpay   (transakcja kartą z zapisaniem karty)
aplikacja ──▶ strona płatności Tpay (karta, 3-D Secure) ──▶ powrót: /billing/return?payment=…
Tpay ──powiadomienie (JWS + md5)──▶ POST /api/billing/notifications/ ──▶ plan aktywny, token karty zapisany
Celery beat co 15 min ──▶ renew_subscriptions ──▶ obciążenie zapisanej karty (cof: recurring)
Celery beat co 5 min ──▶ reconcile_payments ──▶ pyta operatora o płatności, które wciąż czekają
```

1. Aplikacja zapisuje dane do faktury, a potem prosi o płatność za wybrany plan. Backend tworzy
   `Subscription` w stanie `incomplete` i `Payment` (pierwsza płatność) i zakłada transakcję u operatora.
2. Właściciel płaci na stronie operatora. W przeglądarce aplikacja przechodzi na tę stronę,
   na telefonie otwiera ją w systemowej przeglądarce (`expo-web-browser`) i wraca linkiem aplikacji.
3. O wyniku decyduje **powiadomienie od operatora**, nie powrót właściciela (może zamknąć kartę).
   Adres powrotu zawsze niesie numer płatności (`?payment=<id>`). Ekran powrotu odpytuje płatność co 2 s,
   a gdy ta wciąż czeka, backend pyta też operatora (`fetch_result`). To samo robi strona „Plan i płatności”
   i zadanie `reconcile_payments` co 5 minut, więc płatność rozliczy się także bez powiadomienia
   (np. lokalnie) i bez powrotu płacącego. Płatność nieopłacona po dobie kończy się jako niedokończona.
4. Po opłaceniu plan jest `active` na okres planu, token karty jest zapisany (zaszyfrowany),
   a właściciel dostaje e-mail. Od teraz może zakładać sklepy, do `Plan.max_shops`.
5. Gdy okres się kończy, zadanie `renew_subscriptions` (Celery beat) obciąża zapisaną kartę.
   Nowy okres zaczyna się tam, gdzie skończył się poprzedni.

Tpay nie prowadzi subskrypcji sam: daje tokenizację karty przy pierwszej płatności i obciążanie tokenu.
Cykl rozliczeń (odnowienia, ponowienia, wygasanie) jest w [services.py](../backend/billing/services.py).

## Stany planu

| Stan | Znaczenie | Nowe sklepy |
|---|---|---|
| `incomplete` | Czeka na pierwszą płatność (albo ta się nie udała) | nie |
| `active` | Opłacony do `current_period_end` | tak, do limitu planu |
| `past_due` | Odnowienie się nie udało; ponowienie po 1, 3 i 5 dniach (`next_attempt_at`) | nie |
| `canceled` | Anulowany przez właściciela; skończył się z końcem opłaconego okresu | nie |
| `expired` | Wszystkie ponowienia odnowienia nie wyszły albo brak zapisanej karty | nie |

Anulowanie (`cancel_at_period_end`) nie przerywa planu od razu: działa do końca okresu i można je cofnąć.
Istniejące sklepy na razie działają we wszystkich stanach planu; zawieszanie sklepów po końcu planu jest w planie
([ograniczenia-i-plan.md](ograniczenia-i-plan.md)). Dziś sklepy zawiesza tylko zmiana na plan z mniejszym limitem.

Wiadomości e-mail ([emails.py](../backend/billing/emails.py)): plan aktywny, plan przedłużony,
nieudane odnowienie (z datą ponowienia), koniec planu. Po ostatniej nieudanej próbie idzie tylko
„Plan wygasł”, bez „spróbujemy ponownie”.

## Dane do faktury i zgody

- `BillingProfile.kind`: `individual` (imię i nazwisko) albo `company` (nazwa firmy, NIP, osoba do kontaktu).
  Polski NIP jest sprawdzany sumą kontrolną i zapisywany jako 10 cyfr; kod pocztowy w formacie 00-000.
  Firmy spoza Polski podają swój numer VAT.
- Każda płatność zapamiętuje dane do faktury z chwili zapłaty (`Payment.billing_details`).
- Przy płatności właściciel akceptuje regulamin (`terms_accepted_at`). Osoba prywatna dodatkowo prosi
  o rozpoczęcie usługi przed upływem 14 dni na odstąpienie od umowy (`immediate_start_consent_at`).
- Ceny w `Plan.price` są brutto, z VAT `Plan.vat_rate`. Faktur jeszcze nie wystawiamy (KSeF: w planie).

## Operatorzy płatności

Wybiera je zmienna `PAYMENT_GATEWAY`. Oba mają ten sam interfejs ([gateways/base.py](../backend/billing/gateways/base.py)):
`start_payment`, `charge_saved_card`, `parse_notification`, `fetch_result`.

| Operator | Do czego |
|---|---|
| `billing.gateways.fake.FakeGateway` (domyślny) | Symulacja bez konta. Strona płatności to prosta strona backendu (`/api/billing/fake-gateway/<id>/`) z przyciskami „Zapłać kartą testową” i „Odrzuć płatność”. Odnowienia przechodzą, chyba że `FAKE_GATEWAY_DECLINE_RENEWALS=1`. |
| `billing.gateways.tpay.TpayGateway` | Tpay Open API: sandbox (`TPAY_SANDBOX=1`) albo produkcja. |

### Tpay

- Autoryzacja: `POST /oauth/auth` (`client_id`, `client_secret`), token trzymany w pamięci podręcznej do wygaśnięcia.
- Pierwsza płatność: `POST /transactions` z `pay.groupId: 103` i `pay.cardPaymentData.save: 1`;
  `hiddenDescription` to `payment-<id>`, czyli nasze id w powiadomieniu (`tr_crc`).
- Odnowienie: `POST /transactions`, potem `POST /transactions/{id}/pay` z `cardPaymentData.token` i `cof: "recurring"`.
- Powiadomienie (`application/x-www-form-urlencoded`) jest sprawdzane dwa razy:
  - `md5sum` = md5(`id` + `tr_id` + `tr_amount` + `tr_crc` + `TPAY_SECURITY_CODE`);
  - nagłówek `X-JWS-Signature`: certyfikat spod `secure.tpay.com` (sandbox: `secure.sandbox.tpay.com`),
    wydany przez główny certyfikat Tpay i ważny, podpis RSA SHA-256 nad `nagłówek.base64url(treść)`.
  Odpowiedź `TRUE` kończy wysyłanie; inna odpowiedź sprawia, że Tpay ponawia powiadomienie.
- Powtórzone powiadomienie niczego nie zmienia, a zapłacona kwota mniejsza od ceny nie aktywuje planu.

**Konto testowe:** rejestracja na https://register.sandbox.tpay.com, panel https://panel.sandbox.tpay.com.
Klucze API: Integracja → API → Klucze Open API. Kod bezpieczeństwa: Powiadomienia → Bezpieczeństwo.
W sandboksie wynik płatności kartą zależy od końcówki kwoty (np. ,26 to odmowa), a działają tylko karty
testowe z dokumentacji Tpay.

**Powiadomienia lokalnie:** Tpay nie dotrze do `localhost` (dozwolone porty to 80, 443 i 8080).
Pierwsza płatność zadziała i tak, bo platforma sama pyta Tpay o wynik, ale token karty przychodzi tylko
w powiadomieniu, więc plan bez niego wygaśnie zamiast się odnowić. Zapytania do Tpay mają własny
nagłówek `User-Agent`: Cloudflare przed Tpay blokuje domyślny podpis `Python-urllib` (błąd 1010, kod 403). Do sprawdzenia odnowień potrzebny jest publiczny adres, np. tunel do portu 8000,
wpisany w `TPAY_NOTIFICATION_URL`.

## API

| Metoda i ścieżka | Opis |
|---|---|
| `GET billing/plans/` | Plany w sprzedaży (bez logowania), ceny brutto |
| `GET billing/` | `{subscription, profile, payments}`: plan z kartą (bez tokenu), dane do faktury, 12 ostatnich płatności |
| `PUT billing/profile/` | Zapis danych do faktury; `400` z błędami pól |
| `POST billing/checkout/` | `{plan, return_url, accept_terms, immediate_start_consent}` → `201 {payment, redirect_url}`. `400`: brak danych do faktury, zgód albo plan już aktywny; `502`: operator nie odpowiada |
| `GET billing/payments/{id}/` | Stan płatności; gdy czeka, pyta też operatora |
| `POST billing/subscription/cancel/`, `.../resume/` | Anulowanie na koniec okresu i jego cofnięcie |
| `POST billing/subscription/change-preview/` | `{plan, keep_shops?}` → co da zmiana: kierunek, dopłata (`amount_due`, `waived`), saldo, sklepy do zawieszenia i przywrócenia, `blocked`. Niczego nie zmienia |
| `POST billing/subscription/change/` | `{plan, keep_shops?, return_url}` → `200`, gdy plan zmieniony, albo `201` z `payment` i `redirect_url`, gdy najpierw trzeba dopłacić; `400` z powodem blokady |
| `POST billing/notifications/` | Powiadomienia od operatora (nie dla aplikacji) |

`return_url` musi zaczynać się od jednego z `BILLING_RETURN_URL_PREFIXES` (aplikacja w przeglądarce, `mobile://`, `exp://`).
Wszystko poza planami wymaga potwierdzonego e-maila.

## Zmiana planów i cen

Plany są w panelu admina (**Płatności → Plany**): nazwa, cena brutto, VAT, okres w miesiącach, limit sklepów,
pamięć sklepu, wyróżnienie w cenniku, korzyści (lista w JSON), kolejność i widoczność. Migracje dodają:

| Plan | Cena brutto | Sklepy | Pamięć sklepu | Pomoc |
|---|---|---|---|---|
| Start (`start`) | 29 zł / mies. | 1 | 512 MB | e-mailowa |
| Standard (`standard`, polecany) | 49 zł / mies. | 3 | 512 MB | e-mailowa |
| Biznes (`business`) | 99 zł / mies. | 10 | 1 GB | priorytetowa, odpowiedź w ciągu 1 dnia roboczego |

- `max_shops` sprawdza backend przy zakładaniu sklepu (sklepy testowe się nie liczą).
- `shop_memory_mb` to limit pamięci kontenera sklepu, ustawiany przy jego tworzeniu (`ContainerProvisioner`).
  Sklepy testowe i sklepy bez planu dostają `SHOPS_CONTAINER_MEMORY`, a sklepy Magento zawsze co najmniej
  `SHOPS_MAGENTO_MEMORY` (1,5 GB), więcej niż daje dziś którykolwiek plan. Działający kontener zmieni limit
  dopiero po odtworzeniu, np. `update_shop_addresses`.
- Priorytetowa pomoc to obietnica obsługi, nie funkcja aplikacji: trzeba ją zapewnić w pracy zespołu.
- Korzyści w cenniku wpisuj tylko takie, które platforma naprawdę daje.

Zmiana ceny działa od następnego odnowienia, bo odnowienie bierze aktualną cenę planu.

## Zmiana planu

Właściciel z aktywnym planem zmienia go w aplikacji (Plan i płatności → Zmień plan). Nowy plan działa od razu,
a data płatności się nie zmienia ([services.preview_change, change_plan](../backend/billing/services.py)).

- **Wyższy plan:** dopłata = różnica cen × część opłaconego okresu, która została. Najpierw pokrywa ją saldo.
  Dopłata poniżej 5 zł (`MIN_SURCHARGE`) nie jest pobierana: plan zmienia się od razu. Większą właściciel płaci
  na stronie operatora (płatność `upgrade`, jak pierwsza; przy okazji odświeża się zapisana karta), a plan zmienia
  się po jej opłaceniu. Do tego czasu kolejna zmiana jest zablokowana.
- **Niższy plan:** różnica za resztę okresu trafia na saldo (`Subscription.credit`). Odnowienie najpierw zużywa
  saldo; gdy pokrywa ono całą cenę, nie ma obciążenia karty (płatność z `gateway = "credit"`, kwota 0).
- **Sklepy ponad limit nowego planu** są zawieszane (`suspended`): kontener zatrzymany, wolumen i baza zostają.
  Właściciel wybiera, które zostają aktywne (`keep_shops`), domyślnie najstarsze. Sklepu w trakcie zakładania
  nie da się zawiesić. Sklepy testowe nie liczą się do limitu i nigdy nie są zawieszane.
- **Przywracanie:** po zmianie na plan z miejscem zawieszone sklepy wracają same (najstarsze pierwsze);
  inaczej właściciel przywraca sklep przyciskiem (`POST shops/{id}/resume/`), gdy plan ma miejsce.
  Sklep, którego zakładanie się nie skończyło, wraca jako `failed`, gotowy do ponowienia.
- **Pamięć:** gdy nowy plan ma inny `shop_memory_mb`, działające sklepy dostają nowy limit
  (`refresh_shop_resources`: kontener jest odtwarzany, pliki zostają).
- **Blokady:** brak aktywnego planu, zaległa płatność, ten sam plan, plan spoza oferty, niezapłacona dopłata.
- Zmiana planu cofa anulowanie. Właściciel dostaje e-mail „Zmieniliśmy plan na …” z dopłatą albo kwotą na saldo
  i listą zawieszonych lub przywróconych sklepów.

Plan można też nadać ręcznie w panelu admina (**Subskrypcje**), np. dla konta firmowego albo testów:
stan `active` i data końca okresu. Bez zapisanej karty taki plan wygaśnie z końcem okresu.

## Testy

| Plik | Co sprawdza |
|---|---|
| `billing/tests/test_billing.py` | Dane do faktury, zgody, pierwsza płatność przez symulowaną bramkę, odnowienia, ponowienia, wygasanie, anulowanie, idempotencja |
| `billing/tests/test_plan_change.py` | Zmiana planu: dopłata, próg 5 zł, saldo, zawieszanie i przywracanie sklepów, wybór sklepów, blokady, pamięć, odnowienie z saldem |
| `billing/tests/test_tpay.py` | Zapytania do Tpay (podstawione `urlopen`), powiadomienia z prawdziwą weryfikacją JWS na certyfikatach wygenerowanych w teście, w tym próby podrobienia |
