# Obsługa na co dzień

## Zmiana sieci lub adresu IP

Sklepy otwierane z telefonu mają w adresie IP komputera (np. `<slug>.192-168-1-20.sslip.io`).
Po zmianie sieci Wi-Fi albo adresu IP:

```bash
ip route get 1.1.1.1 | grep -oP 'src \K[\d.]+'          # bieżące IP, np. 192.168.1.20
# w .env: SHOPS_BASE_DOMAIN=192-168-1-20.sslip.io
docker compose up -d backend worker                      # wczytanie nowego .env
docker compose exec worker python manage.py update_shop_addresses
```

Polecenie wypisuje każdy sklep ze starym i nowym adresem. Sklep bez kontenera
(np. założony symulatorem) jest pomijany.

W aplikacji: zeskanuj nowy kod QR (pojawia się po ponownym uruchomieniu `npx expo start`)
albo wpisz w Expo Go `exp://<nowe-IP>:8081`, a potem odśwież listę sklepów.

Bez telefonu można wrócić do `SHOPS_BASE_DOMAIN=localhost` i uruchomić to samo polecenie.

## Po restarcie komputera

Kontenery sklepów, Traefik i baza sklepów mają `restart: unless-stopped` i wstają same.
Backend aplikacji trzeba uruchomić:

```bash
docker compose up -d                       # w katalogu głównym
cd infra/shops && docker compose up -d     # na wszelki wypadek, jeśli serwer sklepów nie wstał
cd mobile && npx expo start
```

Objaw niedziałającego serwera sklepów: sklepy nie odpowiadają, a `update_shop_addresses` zgłasza
„Error establishing a database connection”.

## Logi

```bash
docker compose logs -f backend      # zapytania do API
docker compose logs -f worker       # zakładanie sklepów, wysyłka e-maili (treść wiadomości: http://localhost:8030)
docker compose logs -f beat         # harmonogram zadań (odnowienia planów co 15 minut)
docker logs -f shop-<id>            # serwer WWW konkretnego sklepu
docker logs -f shops-proxy          # Traefik
```

Pełny opis błędu kroku zakładania (z wyjątkiem i poleceniem) jest tylko w logach workera.
Użytkownik i panel admina widzą komunikat skrócony.

## Typowe problemy

| Objaw | Przyczyna i rozwiązanie |
|---|---|
| Telefon nie łączy się z Metro | Inna sieć albo sieć izolująca urządzenia (często gościnna lub firmowa). Test: `http://<IP>:8081/status` w przeglądarce telefonu. W ostateczności `npx expo start --tunnel` (wtedy API i sklepy nie są dostępne z telefonu). |
| „Otwórz sklep” na telefonie nie działa | Domena sklepów to `localhost` albo stare IP. Patrz [zmiana sieci](#zmiana-sieci-lub-adresu-ip). |
| Sklep przekierowuje na stary adres | WordPress ma zapisany stary adres. Uruchom `update_shop_addresses`. |
| Brak kodu potwierdzającego albo danych logowania do sklepu | Lokalnie poczta jest w Mailpit: http://localhost:8030. Pusto? Sprawdź `docker compose ps mail` i błędy wysyłki w `docker compose logs worker`. Dane sklepu wyśle ponownie przycisk „Wyślij dane ponownie” w ustawieniach ręcznych. |
| Zmiana w provisioningu nie działa | Worker nie przeładowuje kodu sam: `docker compose restart worker`. |
| Zakładanie stoi na „Oczekuje” | Worker nie działa albo nie widzi Redisa: `docker compose ps`, `docker compose logs worker`. |
| Krok kończy się „Wystąpił nieoczekiwany błąd” | Szczegóły w logach workera. Po naprawie przyczyny użyj „Spróbuj ponownie” w aplikacji. |
| Płatność wisi na „Sprawdzamy płatność…” | Z symulowaną bramką: płatność nie została opłacona na stronie testowej. Z Tpay: powiadomienie nie dociera (lokalnie zwykle tak jest), ekran pyta Tpay sam co kilka sekund. Szczegóły w panelu admina: Płatności → Płatności, i w `docker compose logs backend`. |
| Odnowienia planów się nie wykonują | Działa `beat`? `docker compose ps beat`, `docker compose logs beat`. Zadanie wykonuje worker: `docker compose logs worker`. |
| Właściciel nie może założyć sklepu („Wybierz plan”) | Brak aktywnego planu albo zaległa płatność. Stan w panelu admina: Płatności → Subskrypcje; plan można tam nadać ręcznie. |
| Aplikacja w przeglądarce pokazuje stary kod | Pamięć podręczna Metro: `npx expo start -c`. |

## Ręczne operacje na sklepie

WP-CLI w kontenerze sklepu (zawsze jako `www-data`):

```bash
docker exec -u www-data shop-<id> wp --path=/var/www/html option get home
docker exec -u www-data shop-<id> wp --path=/var/www/html plugin list
```

Ponowne wykonanie jednego kroku zakładania (kroki są idempotentne):

```bash
docker compose exec worker python manage.py shell -c "
from shops.models import Shop
from shops.provisioning import get_provisioner
shop = Shop.objects.get(slug='nazwa-sklepu')
get_provisioner(shop.platform).step_configure_navigation(shop)"
```

Sklepy założone ręcznie skryptem `infra/shops/woocommerce/provision-shop.sh` nie są widoczne w aplikacji.
Usuwa się je skryptem `woocommerce/destroy-shop.sh`.
