# Aplikacja mobilna

Expo SDK 58, React Native 0.88, React 19, Expo Router z typowanymi ścieżkami i React Compilerem.
Jeden kod działa na iOS, Androidzie i w przeglądarce. Kod w [mobile/](../mobile/).

Expo zmienia API między wersjami SDK. Przed użyciem nowego API sprawdź dokumentację dla SDK 58:
https://docs.expo.dev/versions/v58.0.0/. Pakiety instaluj przez `npx expo install <pakiet>`,
żeby dostać wersję zgodną z SDK.

## Struktura

```
mobile/src/
├── app/            ekrany; każdy plik to ścieżka (Expo Router)
├── components/     komponenty współdzielone; ui/ to podstawowe kontrolki
├── constants/      kolory i odstępy (theme), teksty (content, shop-guides), dane marki (brand), strony publiczne (pages)
├── context/        stan globalny: konto (auth) i powiadomienia (notifications)
├── hooks/          useApiQuery, useTheme, useWindowDimensions, useReducedMotion, usePlans, useFullBleed, usePushPermission
└── lib/            klient API, przechowywanie tokenów, typy, drobne narzędzia
```

Zasada: w `app/` są tylko ekrany. Komponenty, hooki i narzędzia są poza tym katalogiem.

## Ekrany i nawigacja

| Ścieżka | Plik | Kto widzi |
|---|---|---|
| `/` | `app/index.tsx` | Wszyscy. Strona główna z ceną „od” (najtańszy plan), pokazem slajdów, czterema krokami (z wyborem planu), motywami, planami i FAQ. |
| `/about` | `app/about.tsx` | Wszyscy. „Jak to działa”, cała lista funkcji i pytań. |
| `/contact` | `app/contact.tsx` | Wszyscy. Dane kontaktowe i formularz. |
| `/pricing` | `app/pricing.tsx` | Wszyscy. Cennik z planami i przejściem do wyboru planu. |
| `/sign-in`, `/sign-up` | `app/sign-in.tsx`, `app/sign-up.tsx` | Tylko niezalogowani |
| `/reset-password` | `app/reset-password.tsx` | Tylko niezalogowani. „Nie pamiętasz hasła?”: adres (podpowiedziany z logowania), potem kod z e-maila i nowe hasło; po zmianie od razu zalogowany |
| `/verify-email` | `app/verify-email.tsx` | Zalogowani bez potwierdzonego e-maila |
| `/shops` | `app/(tabs)/shops.tsx` | Zalogowani z potwierdzonym e-mailem. Lista sklepów. |
| `/help` | `app/(tabs)/help.tsx` | jw. Porady dotyczące prowadzenia sklepu, z wyborem systemu (na start system pierwszego sklepu). |
| `/account` | `app/(tabs)/account.tsx` | jw. Wizytówka konta (zdjęcie profilowe zmieniane kliknięciem, potwierdzony e-mail, plan, staż), konto w skrócie (sklepy względem limitu, a przy sklepie Magento też względem limitu Magento, plan z następną płatnością, dane do faktury), dane profilu, bezpieczeństwo (zmiana hasła, wylogowanie wszędzie, usunięcie konta), skróty i wylogowanie. |
| `/delete-account` | `app/delete-account.tsx` | jw. Usunięcie konta: co zniknie (sklepy z adresami, plan, dane), co zostanie (płatności), anulowanie planu jako alternatywa; usuwa po wpisaniu hasła i potwierdzeniu. Zablokowane, gdy sklep jest zakładany. |
| `/notifications` | `app/notifications.tsx` | jw. Powiadomienia: stan na tym telefonie (włączenie, przejście do ustawień telefonu po odmowie, a w przeglądarce, Expo Go i symulatorze wyjaśnienie), przełączniki tematów i lista telefonów, które je dostają. Link w „Na skróty” na koncie. |
| `/shops/new` | `app/shops/new.tsx` | jw. Formularz nowego sklepu (na telefonie jako okno modalne): najpierw system sklepu (WooCommerce, PrestaShop), pod nim motywy tej platformy. Bez planu zamiast formularza „Najpierw wybierz plan”. |
| `/billing` | `app/billing/index.tsx` | jw. Plan i płatności: stan planu, karta, anulowanie i wznowienie, dane do faktury, historia płatności z linkami do faktur (PDF w przeglądarce). |
| `/billing/change` | `app/billing/change.tsx` | jw. Zmiana planu: podgląd dopłaty albo kwoty na saldo, wybór sklepów, które zostają aktywne, potwierdzenie. |
| `/billing/checkout` | `app/billing/checkout.tsx` | jw. Wybór planu, dane do faktury, zgody i przejście do płatności. |
| `/billing/return` | `app/billing/return.tsx` | jw. Powrót ze strony płatności (`?payment=<id>`): czeka na wynik i prowadzi do zakładania sklepu. |
| `/shops/[id]` | `app/shops/[id].tsx` | jw. Sklep: w trakcie zakładania postęp na paragonie; działający sklep ma kartę z przyciskami (sklep, ustawienia, panel sklepu nazwany jak na jego platformie) na całą szerokość, pod nią listę startową (`ShopChecklist`), kartę sprzedaży (`SalesSummary`: dziś, 30 dni, do obsłużenia, „Zobacz sprzedaż”), dalej „Ustawienia w skrócie” z kafelkami prowadzącymi do sekcji ustawień i paragon obok, dalej porady dla platformy sklepu (przycisk przy poradzie otwiera panel z `admin-access/`) i usuwanie. W przeglądarce strzałka przy tytule cofa także po odświeżeniu strony (`backArrowOptions`). |
| `/shops/[id]/sales` | `app/shops/[id]/sales.tsx` | jw. Sprzedaż działającego sklepu z kopii zamówień: kafelki (dziś, 7 dni, 30 dni ze zmianą względem 30 dni wcześniej), zamówienia do obsłużenia z przejściem do logowania w panelu sklepu, przychód dzień po dniu (wykres albo tabela), 10 ostatnich zamówień ze statusem. Gdy trwa odczyt ze sklepu (`refreshing`), co 2,5 s pyta ponownie, a poprzednie liczby są przygaszone. „Odśwież” zleca odczyt od razu. |
| `/shops/[id]/settings` | `app/shops/[id]/settings.tsx` | jw. Ustawienia działającego sklepu: menu sekcji, które platforma sklepu pozwala zmieniać (`sections` z API), i jedna wybrana sekcja (`?section=platnosci`), regulamin i polityka prywatności (`?section=regulamin`), nowe hasło, usunięcie produktów przykładowych, kopie zapasowe (`?section=kopie`), ustawienia ręczne (logowanie do panelu sklepu), ostatnie zmiany. |

Dostęp do ekranów pilnuje `Stack.Protected` w [app/_layout.tsx](../mobile/src/app/_layout.tsx):
- niezalogowany trafia na stronę główną, zalogowany bez potwierdzonego e-maila na `/verify-email`;
- po zalogowaniu `/sign-in` przekierowuje na `/shops` (albo `/verify-email`).

Strony publiczne (`PublicPages` w [constants/pages.ts](../mobile/src/constants/pages.ts)) nie czekają na sprawdzenie
konta: do jego końca wyglądają jak dla niezalogowanego. Reszta aplikacji czeka, żeby zalogowanego nie odesłać
najpierw do logowania.

Zakładki Sklepy, Pomoc i Konto ([app/(tabs)/_layout.tsx](../mobile/src/app/%28tabs%29/_layout.tsx)):
na telefonie są natywnym paskiem zakładek (`app-tabs.tsx`), a w przeglądarce górnym menu z markizą (`app-tabs.web.tsx`).

## Dane i komunikacja z API

- **[lib/api.ts](../mobile/src/lib/api.ts)** zawiera funkcję `api<T>(ścieżka, {method, body, auth})`.
  - Dodaje token. Przy odpowiedzi `401` raz odświeża parę tokenów i ponawia zapytanie. Jednoczesne odświeżenia współdzielą jedno zapytanie, bo backend rotuje tokeny.
  - Gdy odświeżenie się nie uda, wylogowuje i pokazuje komunikat o wygaśnięciu sesji.
  - Błędy rzuca jako `ApiError` z polskim komunikatem (`message`) i błędami pól (`fieldErrors`).
- **Adres API** to `http://<host Metro>:8000/api`, więc na telefonie w tej samej sieci działa bez konfiguracji. Inny adres można wymusić przez `EXPO_PUBLIC_API_URL`.
- **Pliki** (zdjęcie profilowe) `api` wysyła jako `FormData`, bez nagłówka JSON. Zdjęcie wybiera `expo-image-picker` z kadrowaniem do kwadratu ([lib/avatar.ts](../mobile/src/lib/avatar.ts)), a wgrywa `useAuth().changeAvatar()`.
- **[lib/token-storage.ts](../mobile/src/lib/token-storage.ts):** tokeny trzyma w `expo-secure-store` na telefonie i w `localStorage` w przeglądarce.
- **[hooks/use-api-query.ts](../mobile/src/hooks/use-api-query.ts)** to `useApiQuery<T>(ścieżka, {refetchInterval, enabled})`.
  - Pobiera dane przy każdym wejściu na ekran i odświeża je w odstępach zależnych od danych. Tak lista i szczegóły śledzą zakładanie sklepu.
  - Zwraca `{data, error, isLoading, isStale, isRefreshing, refresh}`.
  - Dane trzyma w pamięci podręcznej ([lib/query-cache.ts](../mobile/src/lib/query-cache.ts)) według ścieżki, wspólnej dla wszystkich ekranów. Ekran otwarty ponownie od razu pokazuje ostatnie dane, a świeże podmienia, gdy przyjdą. Ekrany pytające o tę samą ścieżkę jednocześnie dzielą jedno zapytanie.
  - `isStale` mówi, że dane są kopią z wcześniejszej wizyty. Ekran, który na pierwsze dane reaguje (np. ogłasza koniec zakładania sklepu albo czyta ustawienia ze sklepu), czeka na świeże.
  - `refresh()` po zmianie zawsze wysyła nowe zapytanie, a odpowiedź na wcześniejsze, jeszcze trwające, przepada.
  - Zalogowanie i wylogowanie (także wygaśnięcie sesji) czyści pamięć w `setTokens`, a odpowiedzi na zapytania wysłane wcześniej przepadają. Nowe tokeny tej samej sesji (po zmianie hasła) jej nie czyszczą.
  - Testy zaczynają z pustą pamięcią ([jest.setup.ts](../mobile/jest.setup.ts)).
- **[context/auth.tsx](../mobile/src/context/auth.tsx)** to `useAuth()`: `user`, `signIn`, `signUp`, `signOut`, `verifyEmail`, `resendCode`, `updateProfile`.
- **[context/notifications.tsx](../mobile/src/context/notifications.tsx)** to `useNotify()` z metodami `success(tekst)` i `error(tekst)`.
  - Pokazuje pasek na górze ekranu: zielony na 4 s albo czerwony na 7 s.
  - Wynik każdej operacji (zapis, wysłanie, usunięcie, błąd serwera) zgłaszaj przez ten pasek. Błędy konkretnych pól pokazuj pod polami.

- **[lib/push.ts](../mobile/src/lib/push.ts)** obsługuje powiadomienia push na telefonie.
  - `pushBlocker()` mówi, dlaczego telefon ich nie dostanie: przeglądarka, Expo Go (moduł `expo-notifications` nie jest tam nawet ładowany, bo ostrzega przy imporcie), symulator, brak projektu EAS.
  - `enablePush()` tworzy kanały Androida (po jednym na temat), pyta o zgodę i zgłasza token. `registerDevice()` zgłasza go po cichu, gdy zgoda już jest; `forgetDevice()` przy wylogowaniu.
  - W `app/_layout.tsx` hook `usePushNotifications` zgłasza telefon po zalogowaniu, po powrocie do aplikacji i po zmianie tokenu, a dotknięte powiadomienie otwiera ekran z `data.url` (tylko ścieżki aplikacji).
  - Zachęta `PushPrompt` na ekranie sprzedaży pojawia się, dopóki telefon nie był pytany o zgodę („Nie teraz” do zamknięcia aplikacji).

Typy odpowiedzi API są w [lib/types.ts](../mobile/src/lib/types.ts). Po zmianie API zaktualizuj je ręcznie.

## Wygląd

Motyw graficzny nawiązuje do sklepu przy ulicy. Są w nim trzy elementy:
- markiza w paski (`Awning`) na górze stron i kart;
- zielony szyld („otwarte”) jako kolor główny;
- paragon z kasy (`Receipt`) wszędzie tam, gdzie pokazujemy postęp.

| Plik | Zawartość |
|---|---|
| [constants/theme.ts](../mobile/src/constants/theme.ts) | `Colors` (jasny i ciemny motyw), `Fonts`, `Spacing`, `Radius`, `MaxContentWidth`, `WideBreakpoint` |
| [constants/brand.ts](../mobile/src/constants/brand.ts) | Nazwa i dane kontaktowe. **To wartości tymczasowe do podmiany przed startem.** |
| [constants/content.ts](../mobile/src/constants/content.ts) | Teksty strony głównej: kroki na paragonie, funkcje (slajdy), systemy sklepu (`Platforms`, z planami, w których są), kolory motywów do formularza, FAQ o sklepach (`Faq`) i o planach (`PricingFaq`, też w cenniku, „Jak to działa” i Pomocy). Liczby sklepów i ceny w odpowiedziach trzeba poprawić przy zmianie planów. |
| [constants/shop-guides.ts](../mobile/src/constants/shop-guides.ts) | Porady w szczegółach sklepu i w zakładce Pomoc |

Markiza (`Awning`) wygląda wszędzie tak samo: paski 40×16 px, liczba pasków zależy od szerokości, pierwszy zawsze zielony.
Kolor drugiego paska wybiera tylko `tone`, zależnie od tła pod spodem: `page` (domyślnie, zielony i biały),
`card` na białej karcie (zielony i jasnozielony), `green` na zielonym tle (jasnozielony i biały).
Strona `/docs/` rysuje ten sam wzór w SVG ([page.html](../backend/handbook/templates/handbook/page.html)).

Kolory pobieraj przez `useTheme()`, nie wpisuj ich na sztywno. Wyjątek to zdjęcia i podglądy.
W przeglądarce `useTheme()` daje zmienne CSS (`WebColors`, np. `var(--color-background)`), więc z kolorem nie wolno
robić operacji na tekście (dopisywanie przezroczystości do `#RRGGBB`); przejście do przezroczystości daje `clearOf(kolor)`.
Czcionki: Bricolage Grotesque w nagłówkach, Figtree w tekście, czcionka maszynowa tylko na paragonie.
Na telefonie aplikacja czeka na nie pod ekranem startowym (to pliki w aplikacji), a gdy się nie wczytają, zostaje
czcionka systemowa. W przeglądarce strona nie czeka: do czasu pobrania czcionek tekst jest w czcionce systemowej
(`font-display: swap` i zapasowe kroje w `Fonts`).
Ikony: `Icon` z nazwami z listy w [components/icon.tsx](../mobile/src/components/icon.tsx).
Na iOS to symbole SF, na Androidzie i w przeglądarce Material Symbols.

Szerokie ekrany (od `WideBreakpoint` = 900 px) dostają układ w kolumnach.
Ruch na ekranie (Reanimated) respektuje systemowe ograniczenie ruchu.
Szerokość okna bierz z `useWindowDimensions` z `@/hooks/use-window-dimensions`, a ograniczenie ruchu z `useReducedMotion`
z `@/hooks/use-reduced-motion`, nie z `react-native` i Reanimated (dlaczego: [Strona w przeglądarce](#strona-w-przeglądarce)).

## Strona w przeglądarce

Wersja web działa w trybie serwera (`web.output: "server"`): każdą stronę rysuje serwer Expo, a przeglądarka ją
przejmuje (hydratacja). Strony publiczne przychodzą więc z treścią, tytułem i opisem, które widzą wyszukiwarki
i podglądy linków. Ekrany za logowaniem serwer wysyła puste i z `noindex`, bo nie zna sesji (tokeny są w `localStorage`).

| Plik | Co robi |
|---|---|
| [constants/pages.ts](../mobile/src/constants/pages.ts) | Strony publiczne: ścieżka, tytuł, opis i czy trafia do wyszukiwarek (`indexed`; formularze logowania nie). Nowa strona publiczna musi tu trafić. |
| [app/+html.tsx](../mobile/src/app/+html.tsx) | Dokument wokół każdej strony, tylko na serwerze: `lang="pl"`, tytuł, opis, link kanoniczny, Open Graph, `noindex` dla reszty, ikony, dane strukturalne (Organization, WebSite) na stronie głównej, zmienne kolorów obu motywów. |
| [app/robots.txt+api.ts](../mobile/src/app/robots.txt+api.ts), [app/sitemap.xml+api.ts](../mobile/src/app/sitemap.xml+api.ts) | `robots.txt` (wszystko dozwolone, link do mapy) i mapa strony z publicznych stron z `indexed` ([lib/sitemap.ts](../mobile/src/lib/sitemap.ts)). Wbudowana strona `/_sitemap` Expo Router jest wyłączona (`sitemap: false` w `app.json`). |
| [lib/site.ts](../mobile/src/lib/site.ts) | Adres strony w linkach bezwzględnych: `SITE_URL` albo adres zapytania |
| [lib/plans.ts](../mobile/src/lib/plans.ts) | `loader` strony głównej i cennika: serwer pobiera plany z API, więc ceny są w stronie. `usePlans()` czyta je w przeglądarce z danych strony, a na telefonie z API. |
| `public/` | `og.png` (obrazek podglądu linku, 1200×630), `favicon.svg` i `apple-touch-icon.png` |

Pierwszy render w przeglądarce musi dać to samo co serwer, inaczej React wyrzuca stronę z serwera i rysuje ją od
nowa. Dlatego nic, czego serwer nie wie, nie wpływa na ten render:
- **motyw:** kolory to zmienne CSS ustawiane w `+html.tsx` dla `prefers-color-scheme`, więc strona z serwera ma
  od razu dobre kolory w obu motywach;
- **szerokość okna:** serwer zgaduje ją z nagłówków zapytania (`Sec-CH-UA-Mobile`, inaczej „Mobile” w User-Agent):
  telefon 390 px, reszta 1280 px ([lib/viewport.ts](../mobile/src/lib/viewport.ts)), i zapisuje w
  `<html data-viewport>`. `useWindowDimensions` w przeglądarce podczas hydratacji zwraca tę samą szerokość,
  a zaraz potem prawdziwą (`useSyncExternalStore` z `getServerSnapshot`);
- **ograniczenie ruchu:** `useReducedMotion` w przeglądarce zaczyna od `false` i zmienia się po hydratacji;
- **konto:** do końca sprawdzenia strona wygląda jak dla niezalogowanego, tak jak na serwerze.

Tytuł karty przy przejściach w przeglądarce ustawia układ główny (`documentTitle`): strony publiczne mają swój,
reszta nazwę serwisu.

Serwer deweloperski (`npx expo start`) ładuje ekrany leniwie, więc przeglądarka i tak rysuje stronę od nowa. Zgodność
hydratacji sprawdza się na wersji produkcyjnej: `npx expo export --platform web` tworzy `dist/client` (pliki
statyczne) i `dist/server` (renderowanie, `loader`, `robots.txt`, `sitemap.xml`). Na serwerze uruchamia je Node
z adapterem `expo-server/adapter/express` albo `expo-server/adapter/http` (`createRequestHandler({ build: 'dist/server' })`,
pliki z `dist/client` obok) albo EAS Hosting. Niezgodność widać jako błąd Reacta #418 w konsoli przeglądarki.

## Najważniejsze komponenty

| Komponent | Do czego |
|---|---|
| `Page` | Przewijana strona z wyśrodkowaną treścią, opcjonalnym nagłówkiem i stopką na całą szerokość; dba o klawiaturę. `usePageScroll()` daje sekcjom pozycję przewinięcia. Na wąskich ekranach po przewinięciu o więcej niż ekran pokazuje okrągły przycisk, który od razu przenosi na górę strony (przyklejone sekcje przepuszczają ten skok). |
| `KeyboardArea` | Na Androidzie zmniejsza obszar, gdy otwiera się klawiatura (aplikacja zajmuje cały ekran, więc system tego nie robi) |
| `SiteHeader`, `SiteFooter` | Nagłówek i stopka stron publicznych w przeglądarce |
| `AuthLayout` | Układ logowania, rejestracji i potwierdzania e-maila |
| `ui/Button`, `ui/TextField`, `ui/CodeField`, `ui/ChipSelect`, `ui/SwitchRow`, `ui/Tooltip` | Podstawowe kontrolki. `CodeField` to pole na 6-cyfrowy kod z e-maila (potwierdzenie adresu, nowe hasło). `SwitchRow` to ustawienie włącz/wyłącz z opisem; przełącza je cały wiersz. `Button` delikatnie powiększa się po najechaniu i zapada przy wciśnięciu. |
| `Receipt` | Paragon z wierszami, sumą i pieczątką; po najechaniu unosi się i obraca |
| `ShopSign`, `StatusBadge`, `TestBadge` | Karta sklepu na liście (sklepy zawieszone przez plan wyszarzone i na końcu listy), znacznik statusu i znacznik „Testowy” sklepów sprzed płatnych planów |
| `NewShopButton` | Przycisk nowego sklepu; bez planu prowadzi do wyboru planu, po osiągnięciu limitu planu wyszarzony z dymkiem. Sklepy testowe nie liczą się do limitu (`paidShopCount`). |
| `PlanCard`, `BillingProfileForm` | Plan z ceną brutto, korzyściami i znacznikiem „Polecany” (do wyboru albo z przyciskiem wyrównanym do dołu karty) i formularz danych do faktury (osoba albo firma z NIP) |
| `FeatureSlides` | „Co dostajesz” na całą szerokość pod markizą. Przy przewijaniu przyklejona witryna, w której każde przewinięcie pokazuje następny slajd (`PinnedSequence`); przy ograniczonym ruchu pokaz slajdów ze strzałkami, kropkami i automatycznym przewijaniem. Zdjęcia przechodzą po bokach gradientem w kolor strony (`SIDE_FADE_WIDE`, `SIDE_FADE_NARROW`). |
| `Showcase` | Pasy na całą szerokość (na stronie głównej systemy sklepu z `Platforms` w content.ts): zrzut sklepu przechodzący gradientem w tło. Przy przewijaniu działa jak `FeatureSlides` (`PinnedSequence`); przy ograniczonym ruchu zwykła lista. |
| `PinnedSequence`, `SwapLayer` | Wspólny mechanizm obu sekcji: przyklejenie nagłówka i sceny oraz podmiana elementu co około 160 px przewinięcia (`STEP`, `SWITCH_AT`). W przeglądarce przykleja CSS `sticky`. Na telefonie scena przesuwa się dokładnie o przewinięcie (położenie sekcji jest mierzone tylko przed przyklejeniem, więc nic nie drży), a jedno przesunięcie palcem zmienia najwyżej jeden element: rozpęd zatrzymuje się na następnym, a strona dociąga do pokazanego. `SwapLayer` to jedna warstwa sceny z przenikaniem. |
| `SettingsSection` | Karta jednej sekcji ustawień sklepu; po zmianie pokazuje „Zapisz” i „Cofnij”, każda sekcja zapisuje się osobno |
| `SettingsMenu`, `SettingsPane` | Menu sekcji ustawień: na szerokim ekranie lista z boku, na wąskim przewijany pasek nad treścią, z kropką przy sekcji z niezapisanymi zmianami. `SettingsPane` wsuwa nowo wybraną sekcję od strony ruchu w menu (z dołu lub góry obok listy, z boku pod paskiem). |
| `CtaBand` | Zielony pas z wezwaniem do działania na końcu strony |
| `FaqList` | Pytania i odpowiedzi; odpowiedź rozsuwa się płynnie, strzałka obraca się razem z nią, otwarte jest jedno pytanie naraz |
| `SectionHeader` | Tytuł i wstęp sekcji strony głównej (używany przez sekcje przyklejane) |
| `BackupsSettings` | Sekcja „Kopie zapasowe” w ustawieniach sklepu: „Zrób kopię” (bez potwierdzenia, z liczbą kopii, które zostały na dziś), lista kopii z czasem („Dziś, 03:00”, „16 listopada, 03:00”), rodzajem i rozmiarem, „Przywróć” przy każdej. Przywrócenie wymaga potwierdzenia, które mówi, co zniknie, że sklep będzie przez chwilę nieczynny i że obecny stan da się odzyskać. Pusta lista mówi, kiedy powstanie pierwsza kopia. Wynik obu operacji zgłasza pasek powiadomień ekranu ustawień, a lista odświeża się po nich. |
| `ShopLoginSteps`, `ShopGuidesPanel` | Kroki logowania do panelu sklepu w „Ustawieniach ręcznych”: przycisk do panelu, adres, na który wysłano login i hasło, i „Wyślij dane ponownie”. Danych logowania aplikacja nie pokazuje. Obok porady jako slajdy, osobne dla WooCommerce, PrestaShop i Magento: w WooCommerce przycisk otwiera właściwą stronę panelu, w PrestaShop i Magento stronę startową (ich adresy stron w panelu wymagają tokenu sesji), a porada podaje drogę w menu. |
| `SalesChart` | Przychód z 30 dni jako cienkie słupki (kolor `chart`). Najechanie, dotknięcie albo fokus pokazuje dzień nad wykresem; skala kończy się na okrągłej kwocie (`scaleTop`). Przełącznik „Tabela” pokazuje te same liczby wierszami, od najnowszego dnia. |
| `Badge` | Znacznik z kropką i nazwą stanu; `StatusBadge` (sklep) i statusy zamówień (`ORDER_STATUS_COLORS` w [lib/sales.ts](../mobile/src/lib/sales.ts)) go używają |
| `ShopChecklist` | Lista startowa nowego sklepu (`GET /shops/{id}/checklist/`): pasek postępu i kroki, które platforma odhacza sama (płatności, wysyłka, regulamin, własny produkt, bez produktów przykładowych, powiadomienia, próbne zamówienie). Rozwinięty jest jeden krok: dotknięty albo następny do zrobienia, z opisem i przyciskiem (sekcja ustawień, panel sklepu, usunięcie przykładowych produktów, ekran powiadomień, sklep). Gdy trwa liczenie albo zmiana w sklepie (`refreshing`), co 2,5 s pyta ponownie. „Ukryj listę” pyta o potwierdzenie, a po zrobieniu wszystkich kroków ukrywa ją od razu. |
| `ShopOverview` | Kafelki ze stanem ustawień sklepu; brak płatności lub wysyłki jest wyróżniony (`missingForSales`), kafelek otwiera swoją sekcję ustawień |
| `OnlinePayment` | Operator płatności online w sekcji „Płatności” (Przelewy24, PayU; tylko operatorzy z `payment_operators`): włącznik, tryb testowy, identyfikatory i klucze. Pola kluczy są ukryte; gdy sklep ma już klucze w tym trybie, są puste z kropkami i podpowiedzią, że nowy klucz wpisuje się tylko przy zmianie. Przy Przelewy24 adres IP serwera do wpisania w panelu operatora (`server_ip`). |
| `DocumentsSettings`, `DocumentText` | Sekcja „Regulamin” ustawień sklepu: włącznik dokumentów z aplikacji (z ostrzeżeniem, że zastąpią obecne strony sklepu, i wyłączony dla sklepów spoza Polski), dane sprzedawcy (pola NIP, KRS i REGON zależą od formy działalności), zwroty i czas wysyłki, uwaga o prawniku, linki do opublikowanych stron. „Podgląd dokumentów” wysyła niezapisane zmiany do `documents/preview/` i pokazuje regulamin albo politykę prywatności jako tekst (`DocumentText`: nagłówki, akapity, listy z jednym poziomem zagnieżdżenia); błędy trafiają pod pola. |
| `Note` | Szara (albo ostrzegawcza, `warning`) ramka z krótką uwagą pod polami formularza |

Hook `useFullBleed` pozwala sekcji wyjść z wyśrodkowanej kolumny na całą szerokość strony.

## Płatności w aplikacji

[lib/payment.ts](../mobile/src/lib/payment.ts): `goToPayment(checkout)` w przeglądarce przechodzi na stronę płatności
(powrót przekierowaniem), a na telefonie otwiera ją w systemowej przeglądarce (`expo-web-browser`,
`openAuthSessionAsync`) z powrotem przez `Linking.createURL('/billing/return')`. Po opłaceniu ekran powrotu
odświeża konto (`useAuth().refreshUser()`), bo plan i limit sklepów aplikacja czyta z użytkownika.

## Obrazy

| Katalog | Co | Skąd |
|---|---|---|
| `assets/images/features/` | Zdjęcia slajdów „Co dostajesz” | Zmniejszone zdjęcia; oryginały w pełnej rozdzielczości nie są przechowywane w repozytorium |
| `assets/images/themes/` | Podglądy motywów | Zrzuty ekranu sklepów założonych przez aplikację, 1200×750 |

Ikona strony (`public/favicon.svg`, `public/apple-touch-icon.png` i `assets/images/favicon.png`, z którego Expo robi
`favicon.ico`) to znak z logo: markiza nad drzwiami na zielonym tle. `public/og.png` powtarza górę strony głównej
(nagłówek i paragon z pieczątką „Otwarte”); przy zmianie hasła strony albo marki trzeba go narysować na nowo.

Proporcje zdjęć są zapisane obok nich w `content.ts` (`aspectRatio`). W przeglądarce `Image`
nie dopasowuje się sam do proporcji, więc po podmianie zdjęcia trzeba je poprawić.

## Uruchamianie i sprawdzanie

```bash
npx expo start          # w: przeglądarka, kod QR: Expo Go
npx tsc --noEmit        # typy
npx expo lint           # lint
npm test                # testy (Jest z jest-expo i React Native Testing Library)
npm run test:coverage   # testy z pokryciem kodu; raport w coverage/lcov-report/index.html
```

Podgląd na telefonie: [uruchomienie.md](uruchomienie.md#podgląd-na-telefonie). Powiadomienia push wymagają buildu aplikacji: [uruchomienie.md](uruchomienie.md#powiadomienia-push).

## Testy

Testy leżą w katalogach `__tests__` (testy ekranów w `src/__tests__/`), nigdy w `src/app/`, bo tam każdy plik
jest ekranem. Konfiguracja Jest jest w `package.json`. Resolver Reanimated ładuje webowe wersje Reanimated
i Worklets, więc animacje działają w testach bez natywnego środowiska.

Pomocnicze pliki w `src/testing/`:

| Plik | Do czego |
|---|---|
| `router.ts` | Atrapa `expo-router`: `jest.mock('expo-router', () => require('@/testing/router'))`. `Link` przy naciśnięciu woła `router.push(href)`, a parametry adresu ustawia się przez `useLocalSearchParams.mockReturnValue`. |
| `api.ts` | `mockApi({'GET /shops/7/': …})` odpowiada na `api()` według metody i ścieżki. Tablica to kolejne odpowiedzi, a `Error` jest rzucany. `sent(klucz)` zwraca wysłane treści. |
| `fixtures.ts` | `shopSettings()` i `shopDetail()`: przykładowe odpowiedzi API do nadpisania w teście |
| `react-dom-server.d.ts` | Typ `renderToStaticMarkup`, którym `seo.test.tsx` rysuje `+html.tsx` jak serwer |

Testy sprawdzają to, co widzi użytkownik: szukają elementów po roli i nazwie (`getByRole('button', {name: 'Zapisz'})`),
nie po identyfikatorach. Dlatego pola formularzy mają `accessibilityLabel` z widocznej etykiety.
React Native Testing Library 14 renderuje asynchronicznie: `await render(...)` i `await fireEvent.press(...)`.

Atrapa `Link` zgłasza błąd, gdy element owinięty przez `asChild` dostaje tablicę stylów, tak jak prawdziwy
Expo Router. Taki element dostaje jeden obiekt stylów (`StyleSheet.flatten`); funkcji stylu `asChild` też nie przekazuje.

Nietestowane zostają głównie animacje strony głównej (przyklejane sekcje, pokaz slajdów), układy nawigacji
i pliki tylko dla przeglądarki (`*.web.ts`; Jest uruchamia wersje na telefon). Opis strony dla wyszukiwarek
(`+html.tsx`, mapa strony, zgadywanie szerokości okna, zmienne kolorów) sprawdza `seo.test.tsx`.
