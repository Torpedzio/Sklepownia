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
docker compose logs -f beat         # harmonogram zadań (odnowienia planów co 15 minut, monitor co 5)
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
| Sklep nie wysyła e-maili (brak ich w http://localhost:8031) | Sklep sprzed poczty albo zawieszony w trakcie zmiany: `docker compose exec worker python manage.py configure_shop_mail <slug>`. Działa `shops-mail`? `cd infra/shops && docker compose ps mail`. |
| Zmiana w provisioningu nie działa | Worker nie przeładowuje kodu sam: `docker compose restart worker`. |
| Zakładanie stoi na „Oczekuje” | Worker nie działa albo nie widzi Redisa: `docker compose ps`, `docker compose logs worker`. |
| Krok kończy się „Wystąpił nieoczekiwany błąd” | Szczegóły w logach workera. Po naprawie przyczyny użyj „Spróbuj ponownie” w aplikacji. |
| Płatność wisi na „Sprawdzamy płatność…” | Z symulowaną bramką: płatność nie została opłacona na stronie testowej. Z Tpay: powiadomienie nie dociera (lokalnie zwykle tak jest), ekran pyta Tpay sam co kilka sekund. Szczegóły w panelu admina: Płatności → Płatności, i w `docker compose logs backend`. |
| Odnowienia planów się nie wykonują | Działa `beat`? `docker compose ps beat`, `docker compose logs beat`. Zadanie wykonuje worker: `docker compose logs worker`. |
| Faktura „w przygotowaniu” nie przychodzi | Panel admina: Płatności → Faktury, kolumna błędu. `pending`: wystawienie się nie udało (np. brak `INVOICE_SELLER_*` albo Fakturownia nie odpowiada); `process_invoices` ponawia co jakiś czas, akcja „Wystaw teraz” od razu. `rejected`: KSeF odrzucił fakturę; popraw ją w Fakturowni, wyślij tam do KSeF i użyj akcji „Sprawdź ponownie w KSeF”. |
| Sprzedaż w aplikacji pokazuje „Nie udało się odczytać zamówień ze sklepu” albo stare liczby | Szczegóły w `docker compose logs worker` („Reading the orders of shop …”). Sklep musi działać (`active`), a jego kontener odpowiadać. Odczyt zleca `beat` co `SHOP_ORDERS_SYNC_MINUTES` minut, „Odśwież” w aplikacji od razu. Po zmianie kodu odczytu: `docker compose restart worker`. |
| Lista startowa nie odhacza produktu albo produktów przykładowych | Liczenie robi worker przy otwarciu ekranu sklepu, najwyżej raz na 2 minuty; błędy w `docker compose logs worker` („Counting the products of shop …”). Stan sprawdzisz w powłoce Django: `ShopChecklist.objects.get(shop_id=…)`. Liczą się produkty w każdym stanie poza koszem, przykładowe rozpoznawane jak przy ich usuwaniu. |
| Powiadomienia push nie przychodzą | Ekran Konto → Powiadomienia: czy telefon jest na liście i czy temat jest włączony. Aplikacja z Expo Go albo bez projektu EAS ich nie dostaje ([uruchomienie.md](uruchomienie.md#powiadomienia-push)). Błędy wysyłki i potwierdzeń: `docker compose logs worker` („Push to device”). Telefony w panelu admina: Powiadomienia push. O zamówieniach powiadomienie przychodzi przy odczycie sklepu, do 15 minut po złożeniu. |
| Włączenie Przelewy24 albo PayU kończy się błędem „Nie udało się pobrać wtyczki…” | Worker nie dosięga strony operatora: sprawdź sieć workera i adres w `ONLINE_PAYMENTS` (woocommerce.py, prestashop.py). „…różni się od wersji sprawdzonej przez nas”: operator podmienił plik pod tym samym adresem. Pobierz go, sprawdź i wpisz nową wersję z sumą SHA-256 albo zostaw starą. Pobrane pliki są w `SHOPS_PACKAGE_CACHE` workera. |
| Klienci nie mogą zapłacić przez Przelewy24 | Zwykle adres IP serwera nie jest dodany w panelu Przelewy24 albo klucze są z innego trybu (testowy i produkcyjny mają różne). Adres, który pokazuje aplikacja, ustawisz w panelu admina: Serwery → `public_ip`. Ustawienia wtyczki sprawdzisz w panelu sklepu. |
| Zapis ustawień kończy się „Nie udało się opublikować regulaminu i polityki prywatności…” albo dokumenty w sklepie są stare | Publikację robi worker przy zapisie, gdy w sekcji Regulamin dokumenty są włączone. Pozostałe zmiany z tego zapisu są już w sklepie; przyczyna w `docker compose logs worker` („Shop operation … failed”). Po zmianie wzorów (nowe `documents.VERSION`): `docker compose exec backend python manage.py publish_shop_documents`. Magento: po zmianie modułu przebuduj obraz (`cd infra/shops && docker compose build magento`); kontener sklepu odtworzy się przy następnej publikacji. |
| Właściciel nie może założyć sklepu („Wybierz plan”) | Brak aktywnego planu albo zaległa płatność. Stan w panelu admina: Płatności → Subskrypcje; plan można tam nadać ręcznie. |
| Przywrócenie kopii kończy się „…Sklep ma z powrotem stan sprzed próby” | Przyczyna w `docker compose logs worker` („Restoring backup … failed”). Sklep działa w stanie sprzed próby, a na liście jest kopia tego stanu. Przy „…ani wrócić do stanu sprzed próby” sklep potrzebuje ręki: `restore_shop <id>` i najnowsza kopia „Stan sprzed przywrócenia kopii”. |
| Aplikacja w przeglądarce pokazuje stary kod | Pamięć podręczna Metro: `npx expo start -c`. |
| Właściciel dostał „Sklep nie działa” | Co widzi monitor i co naprawiał: e-mail obsługi albo panel admina, Monitorowanie → Awarie. Logi sklepu: `docker logs shop-<id>`, naprawy: `docker compose logs worker` („Repairing shop …”). Po naprawie najbliższa runda (do 5 minut) wyśle „znowu działa”; od razu: `check_shops <slug>`. |
| Monitor nie sprawdza sklepów | Działają `beat` i worker? Panel admina, Monitorowanie → Ostatnie uruchomienia: `monitor`. Runda pomija sklepy, w których worker coś robi (np. przywraca kopię), a wszystkie, gdy nie działa Docker, proxy albo baza sklepów (wtedy obsługa dostaje e-mail). |

## Monitorowanie

Jak działa: [architektura.md](architektura.md#monitorowanie). Awarie, stan sklepów i ostatnie uruchomienia są
w panelu admina: Monitorowanie (tylko do odczytu). E-maile dla obsługi idą na `ALERT_EMAILS` (domyślnie
`CONTACT_EMAIL`), lokalnie do Mailpit: http://localhost:8030.

```bash
docker compose exec worker python manage.py check_shops [<slug>…]                  # runda teraz, z wynikiem
docker compose exec worker python manage.py update_shop_containers --dry-run       # które kontenery są nieaktualne
docker compose exec worker python manage.py update_shop_containers [<slug>…]       # zastąpienie ich
```

`check_shops` robi to, co runda z harmonogramu, łącznie z naprawami i powiadomieniami. Ze slugami sprawdza tylko
te sklepy (usługi, dysk i kopie zawsze).

**Kontenery sprzed healthchecka.** Nowe i przywrócone sklepy dostają healthcheck od razu, starsze dopiero po
`update_shop_containers`. Polecenie zastępuje też kontenery ze starym obrazem albo limitem pamięci. Pliki sklepu
są w wolumenie, a baza w `shops-db`, więc nic nie ginie, ale sklep nie odpowiada przez kilkanaście sekund (Magento
dłużej): uruchamiaj je poza godzinami ruchu. Sklepy, w których worker coś robi, pomija.

**Sklep bez kontenera i wolumenu** (np. pliki usunięte ręcznie) monitor tylko zgłasza: nowy kontener byłby pustym
sklepem. Taki sklep przywróć z kopii (`restore_shop`) albo usuń.

**Pilnowanie monitora.** Gdy padnie worker albo beat, rundy ustają bez alarmu. Ustaw `MONITOR_PING_URL` na adres
usługi typu „dead man's switch” (np. Healthchecks.io z okresem 5 minut): monitor pinguje ją po każdej rundzie, a ona
alarmuje, gdy pingi ustaną.

## Kopie zapasowe

Jak działają: [infra/shops/README.md](../infra/shops/README.md#kopie-zapasowe). Kopie i ich błędy widać w panelu
admina: Shops → Shop backups (tylko do odczytu). Polecenia uruchamia worker, bo tylko on ma dostęp do Dockera:

```bash
docker compose exec worker python manage.py backup_shops <slug> [<slug>…]   # kopia wybranych sklepów teraz
docker compose exec worker python manage.py backup_shops                    # wszystkie sklepy i porządki jak w nocy
docker compose exec worker python manage.py restore_shop <id|slug>          # kopie sklepu z numerami
docker compose exec worker python manage.py restore_shop <id|slug> --backup <numer>
```

Przywrócenie działającego sklepu działa jak w aplikacji: najpierw kopia obecnego stanu, a gdy przywrócenie się nie
uda, sklep wraca do niej.

**Usunięty sklep** wraca w ciągu 14 dni od usunięcia z kopii „Stan sprzed usunięcia sklepu”: `restore_shop <id>`
(numerem, bo adres mógł już zająć inny sklep). Polecenie odtwarza kontener, bazę i pliki, ustawia sklep jako
działający i odczytuje go na nowo. Odmówi, gdy adres ma już inny sklep. Ostrzeże, gdy właściciel ma teraz więcej
sklepów, niż pozwala jego plan: wtedy ustal z nim, co dalej (np. zawieszenie innego sklepu). Sklep usuniętego
konta nie ma kopii.

Gdy kopie się nie robią albo w części sklepów się nie udały, obsługa dostaje e-mail od monitora. Działa `beat`
(`docker compose ps beat`)? Jest `SHOPS_BACKUP_PASSWORD` w `.env` workera i obraz `shops/backup:0.19.1`
(`cd infra/shops && docker compose build backup`)? Błąd każdej kopii jest w panelu admina i w `docker compose logs
worker` („Backing up shop …”). Zostały kontenery narzędzia (`docker ps -a --filter label=shops.backup`)? Usuwa je
nocny przebieg.

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
