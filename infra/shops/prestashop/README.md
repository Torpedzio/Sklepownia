# Sklepy PrestaShop

Sklepy PrestaShop 9 działają na oficjalnym obrazie `prestashop/prestashop:9.2.1-apache` (`SHOPS_PRESTASHOP_IMAGE`),
bez własnego Dockerfile. Pliki sklepu są w wolumenie `shop-<id>` na `/var/www/html`.
Backend: [prestashop.py](../../../backend/shops/platforms/prestashop.py), wszystko w sklepie robi skryptami PHP.
Pierwsze zakładanie pobiera obraz (~1 GB), jeśli go nie ma: `docker pull prestashop/prestashop:9.2.1-apache`.

## Kroki i czasy

Baza i miejsce na serwerze jak w [README serwera](../README.md).

| Krok | Co robi | Czas |
|---|---|---|
| Uruchomienie sklepu | kontener z `PS_INSTALL_AUTO=0`, wolumen na `/var/www/html`; gotowy, gdy Apache odpowiada | ~5 s |
| Sklep, język i konto administratora | `install/index_cli.php` z językiem, krajem, strefą czasową, motywem, bez danych demo (`--fixtures=0`); zapis losowego folderu panelu w `Shop.admin_path`; login (e-mail) i hasło pracownika | ~80 s |
| Waluta, koszyk i zamówienia | waluta (import z `localization/<kraj>.xml`, gdy jej nie ma), nazwa i e-mail sklepu, zakupy bez konta, stany magazynowe; wyłączenie płatności czekiem, przelewem i przy odbiorze oraz treści demo na stronie głównej (`ps_imageslider`, `ps_customtext`, `ps_banner`) | ~15 s |
| Kategorie produktów | kategorie pod „Strona główna” i opcjonalnie 6 przykładowych produktów (też na stronie głównej) | ~2 s |
| Menu, wyszukiwarka i filtry | menu górne z kategorii (`MOD_BLOCKTOPMENU_ITEMS`), szablon filtrów `ps_facetedsearch` (kategorie, cena, dostępność), indeks cen | ~3 s |
| Końcowe sprawdzenie | strona główna i strona logowania panelu (`/<folder>/login`) przez proxy, obie 200 | ~6 s |

Z aplikacji zmienia się podstawowe dane, otwarcie sklepu, płatności i motyw; resztę w panelu PrestaShop.

## Uwagi techniczne

- **Panel** dostaje przy instalacji losową nazwę folderu (`admin` + znaki), co chroni go przed botami.
  Pracownik loguje się e-mailem; backend zapisuje go w `ShopCredentials.admin_login`.
- **Skrypty PHP** (`PrestaShopProvisioner._php`) ładują `config/config.inc.php` z kontekstem sklepu, języka i pierwszego
  superadministratora, jako `www-data`, żeby pliki pamięci podręcznej należały do serwera WWW. Każdy trwa ~1 s.
- **Waluta:** `new Currency()` zostawia pustą nazwę, symbol i format. Waluta musi przyjść z pakietu lokalizacji,
  a ten potrzebuje jądra Symfony panelu (`AdminKernel`), co kosztuje ~12 s. Dlatego jądro uruchamia tylko ten krok.
- **Motyw:** `bin/console prestashop:theme:enable` w 9.2 kończy się błędem kontekstu języka.
  Działa `ThemeManagerBuilder(...)->build()->enable()` i czyszczenie pamięci podręcznej.
- **Filtry:** `ps_facetedsearch::createDefaultTemplate()` tworzy szablon tylko z produktów z kombinacjami
  (łączy tabelę kombinacji przez `INNER JOIN`), więc przy prostych produktach nic nie powstaje. Szablon zapisujemy sami.
- **Adres** sklepu jest w tabeli `ps_shop_url` i w `PS_SHOP_DOMAIN`; `update_shop_addresses` podmienia oba
  i odtwarza `.htaccess`.
- **Poczta:** moduł `sklepowniamail` (zapisywany przez backend w `modules/`) zmienia nadawcę w haku
  `actionEmailSendBefore`, a PrestaShop wysyła przez SMTP przekaźnika ([poczta sklepów](../README.md#poczta-sklepów)).
  `PS_SHOP_EMAIL` zostaje adresem właściciela: pokazuje go sklep i na niego idą odpowiedzi.
- **Braki:** logo „my store” z motywu zostaje do wymiany w panelu; część napisów motywu Hummingbird
  nie ma polskiego tłumaczenia („Search products…”, stopka).
