# Serwer sklepów

Tu działają sklepy klientów, każdy we własnym kontenerze. Klient wybiera system sklepu w formularzu:

| Platforma | Obraz | Opis kroków i pułapek |
|---|---|---|
| WordPress + WooCommerce | `shops/wordpress:7.1`, budowany z [woocommerce/](woocommerce/) | [woocommerce/README.md](woocommerce/README.md) |
| PrestaShop 9 | oficjalny `prestashop/prestashop:9.2.1-apache` | [prestashop/README.md](prestashop/README.md) |
| Magento (Mage-OS 4) | `shops/magento:4.0.0`, budowany z [magento/](magento/) | [magento/README.md](magento/README.md) |

Sklepy zakłada backend: worker Celery wykonuje kroki provisionera platformy
([backend/shops/platforms/](../../backend/shops/platforms/)) przez socket Dockera. Wspólna obsługa kontenerów
(serwer, baza, kontener, wolumen, usuwanie) jest w
[container.py](../../backend/shops/provisioning/container.py), a kroki i ustawienia każdej platformy
w [platforms/\_\_init\_\_.py](../../backend/shops/platforms/__init__.py).

Sklepy z backendu mają kontener i wolumen `shop-<id>` oraz bazę `shop_<id>`.
Sklepy ze skryptu [woocommerce/provision-shop.sh](woocommerce/provision-shop.sh) nazywają się według sluga
(`shop-<slug>`), więc obie pule się nie mieszają.
Całość systemu: [docs/architektura.md](../../docs/architektura.md).

```
przeglądarka ──▶ Traefik :8080 ──Host: <slug>.<SHOPS_BASE_DOMAIN>──▶ kontener shop-<id> (WooCommerce / PrestaShop / Magento)
                      │                                                  │
                      └── adres bez działającego sklepu ──▶ platforma: strona „Sklep chwilowo niedostępny”
                                       MariaDB (shops-db): osobna baza i użytkownik na sklep
                                       OpenSearch (shops-search): wyszukiwarka sklepów Magento, indeksy shop_<id>_*
                                       Mailpit (shops-mail): poczta wysłana przez sklepy, podgląd :8031
```

## Uruchomienie

```bash
cd infra/shops
cp .env.example .env                       # wpisz SHOPS_DB_ROOT_PASSWORD (i SHOPS_FALLBACK_URL poza tym komputerem)
docker compose build wordpress magento     # obrazy sklepów; Magento buduje się ~10 min
docker compose up -d                       # Traefik, MariaDB, OpenSearch i Mailpit sklepów
```

Obraz PrestaShop pobiera się sam przy pierwszym sklepie, ale lepiej zrobić to od razu:
`docker pull prestashop/prestashop:9.2.1-apache` (~1 GB).
Bez sklepów Magento można pominąć `magento` w `build` i uruchomić tylko `docker compose up -d proxy db mail`.

Sklepy są na porcie **8080**, żeby nie kolidować z innymi serwerami na 80/443.
Przeglądarki i curl same rozwiązują `*.localhost` na 127.0.0.1, więc nie trzeba konfigurować DNS.

## Poczta sklepów

Sklepy wysyłają e-maile (potwierdzenia zamówień, konta klientów, powiadomienia właściciela o zamówieniach) przez
przekaźnik w sieci `shops`: `SHOPS_SMTP_HOST:SHOPS_SMTP_PORT`, lokalnie Mailpit `shops-mail:1025`, podgląd
http://localhost:8031. Sklep nie loguje się do przekaźnika: właściciel sklepu może odczytać wszystko, co sklep ma
w ustawieniach, więc dane logowania do dostawcy poczty trzyma tylko przekaźnik.

Nadawcą jest zawsze `<slug>@SHOPS_MAIL_DOMAIN` z nazwą sklepu, bo dostawca poczty podpisze tylko adresy z własnej
domeny. Adres, z którego wiadomość wysłał sam system sklepu (zwykle adres kontaktowy właściciela), trafia do Reply-To,
chyba że wiadomość już je ma (np. powiadomienie o zamówieniu odpowiada klientowi). Ustawienia właściciela
w sklepie się nie zmieniają. Zasadę wdraża każda platforma po swojemu:

| Platforma | Gdzie | Serwer SMTP |
|---|---|---|
| WooCommerce | wtyczka „must-use” [sklepownia-mail.php](../../backend/shops/platforms/files/woocommerce/sklepownia-mail.php) (hak `phpmailer_init`) | opcja `sklepownia_mail` |
| PrestaShop | moduł [sklepowniamail](../../backend/shops/platforms/files/prestashop/sklepowniamail/sklepowniamail.php) (hak `actionEmailSendBefore`) | `PS_MAIL_METHOD=2`, `PS_MAIL_SERVER`, `PS_MAIL_SMTP_PORT` |
| Magento | wtyczka [MailSender](magento/Sklepownia/Provisioning/Plugin/MailSender.php) w obrazie (`TransportInterface::sendMessage`) | `system/smtp/*`, nadawca w `sklepownia/mail/sender` |

Pliki WooCommerce i PrestaShop backend zapisuje w wolumenie sklepu, bo te platformy trzymają tam swój kod.
Nowe sklepy dostają pocztę przy zakładaniu, istniejące poleceniem (kontener ze starszego obrazu jest najpierw odtwarzany):

```bash
docker compose exec worker python manage.py configure_shop_mail            # wszystkie działające sklepy
docker compose exec worker python manage.py configure_shop_mail <slug>     # wybrane
```

Magento wysyła kopię każdego potwierdzenia zamówienia do właściciela (`sales_email/order/copy_to`, ukryta kopia),
bo inaczej nie dowiedziałby się o zamówieniu; WooCommerce i PrestaShop mają osobne powiadomienie.

## Pamięć

Limit pamięci kontenera daje plan właściciela (`Plan.shop_memory_mb`), a sklepom testowym i bez planu
`SHOPS_CONTAINER_MEMORY` (512 MB). Magento nie działa na mniej niż ~1,5 GB, więc dostaje co najmniej
`SHOPS_MAGENTO_MEMORY` (1536 MB) niezależnie od planu. OpenSearch zajmuje stale ~1 GB (sterta 512 MB),
także gdy nie ma żadnego sklepu Magento.

## Sklepy na telefonie

Na telefonie `localhost` to sam telefon, więc sklepy potrzebują domeny wskazującej na komputer.
Wystarczy publiczny DNS sslip.io: `<slug>.192-168-1-20.sslip.io` rozwiązuje się na `192.168.1.20`.

```bash
# w głównym .env
SHOPS_BASE_DOMAIN=192-168-1-20.sslip.io
docker compose up -d backend worker
docker compose exec worker python manage.py update_shop_addresses
```

Polecenie odtwarza kontener każdego działającego sklepu z nową regułą Traefika (dane zostają w wolumenie)
i podmienia adres w bazie sklepu: w WordPressie `wp search-replace`, w PrestaShop tabelę `ps_shop_url`,
w Magento `web/unsecure/base_url` i `web/secure/base_url`. Trzeba je powtórzyć, gdy komputer dostanie
inny adres IP, np. w innej sieci Wi-Fi. Niektóre routery blokują domeny wskazujące na adresy prywatne
(ochrona przed DNS rebinding); wtedy sslip.io nie zadziała w tej sieci.
Sklepy ze skryptu `provision-shop.sh` mają adres ustalony przy zakładaniu i polecenie ich nie obejmuje.

## Adres bez działającego sklepu

Traefik zna tylko działające kontenery: zatrzymany kontener (sklep zawieszony przez plan, sklep w trakcie
zakładania przed startem kontenera, kontener, który się restartuje) znika z jego reguł. Takie adresy łapie router
`shop-fallback` z [traefik/fallback.yml](traefik/fallback.yml) (priorytet 1, więc reguła `Host` sklepu zawsze
wygrywa) i wysyła je do platformy pod `SHOPS_FALLBACK_URL/shop-unavailable/`. Adres, o który pytał gość, idzie
w nagłówku `X-Forwarded-Host`, który Traefik ustawia sam (wysłany przez gościa odrzuca).

Platforma sprawdza sklep w swojej bazie ([unavailable.py](../../backend/shops/unavailable.py)) i odpowiada:

| Sklep pod adresem | Odpowiedź |
|---|---|
| zawieszony, działający (kontener się restartuje) albo nieudany | `503`, `Retry-After: 3600`, szyld „Nieczynne” |
| w kolejce albo w trakcie zakładania | `503`, `Retry-After: 300`, szyld „Wkrótce otwarcie” |
| nie ma go, usunięty albo obca domena | `404`, „Nie ma tu sklepu” |

Strona ma nazwę sklepu i jest w jego języku (polski, angielski, niemiecki), bez marki platformy.
Kod `503` z `Retry-After` mówi wyszukiwarkom, że przerwa jest chwilowa, więc nie usuwają sklepu z wyników.

`SHOPS_FALLBACK_URL` w `.env` to adres platformy widziany z kontenera Traefika: lokalnie backend na tym
komputerze (`http://host.docker.internal:8000`). Traefik nie przekazuje adresu sklepu w nagłówku `Host`,
więc w `DJANGO_ALLOWED_HOSTS` platformy musi być host z `SHOPS_FALLBACK_URL`. Zmiana pliku lub zmiennej
wymaga odtworzenia proxy: `docker compose up -d proxy` (sprawdź najpierw, że żaden sklep się nie zakłada).

Od startu kontenera do uruchomienia serwera w środku (kilka sekund) reguła sklepu już istnieje, więc gość
dostaje wtedy `502 Bad Gateway` od Traefika, nie tę stronę.

## Uwagi techniczne

- **Każdy krok jest idempotentny.** Ponowne uruchomienie dokańcza sklep (w aplikacji: „Spróbuj ponownie”).
  Backend zapisuje hasła (bazy, admina, API) w `ShopCredentials` **zanim** ich użyje.
- **Nowy krok:** dopisz parę `(klucz, etykieta)` do kroków platformy w
  [platforms/\_\_init\_\_.py](../../backend/shops/platforms/__init__.py), metodę `step_<klucz>` do jej provisionera
  i wiersz do tabeli kroków w README platformy.
- **Nazwy kategorii:** backend dobiera je do branży i liczby kategorii
  ([categories.py](../../backend/shops/categories.py)).
- **Dostęp do Dockera:** Traefik i worker backendu używają `docker.sock` (na systemach z SELinux z `label=disable`).
  Dla workera to w praktyce uprawnienia roota; przed produkcją trzeba go odseparować
  ([docs/ograniczenia-i-plan.md](../../docs/ograniczenia-i-plan.md)).
