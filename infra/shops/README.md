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
                                                                         │
                                       MariaDB (shops-db): osobna baza i użytkownik na sklep
                                       OpenSearch (shops-search): wyszukiwarka sklepów Magento, indeksy shop_<id>_*
```

## Uruchomienie

```bash
cd infra/shops
cp .env.example .env                       # wpisz SHOPS_DB_ROOT_PASSWORD
docker compose build wordpress magento     # obrazy sklepów; Magento buduje się ~10 min
docker compose up -d                       # Traefik, MariaDB i OpenSearch
```

Obraz PrestaShop pobiera się sam przy pierwszym sklepie, ale lepiej zrobić to od razu:
`docker pull prestashop/prestashop:9.2.1-apache` (~1 GB).
Bez sklepów Magento można pominąć `magento` w `build` i uruchomić tylko `docker compose up -d proxy db`.

Sklepy są na porcie **8080**, żeby nie kolidować z innymi serwerami na 80/443.
Przeglądarki i curl same rozwiązują `*.localhost` na 127.0.0.1, więc nie trzeba konfigurować DNS.

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
