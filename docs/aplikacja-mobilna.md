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
├── constants/      kolory i odstępy (theme), teksty (content, shop-guides), dane marki (brand)
├── context/        stan globalny: konto (auth) i powiadomienia (notifications)
├── hooks/          useApiQuery, useTheme, useFullBleed
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
| `/verify-email` | `app/verify-email.tsx` | Zalogowani bez potwierdzonego e-maila |
| `/shops` | `app/(tabs)/shops.tsx` | Zalogowani z potwierdzonym e-mailem. Lista sklepów. |
| `/help` | `app/(tabs)/help.tsx` | jw. Porady dotyczące prowadzenia sklepu. |
| `/account` | `app/(tabs)/account.tsx` | jw. Wizytówka konta (zdjęcie profilowe zmieniane kliknięciem, potwierdzony e-mail, plan, staż), konto w skrócie (sklepy względem limitu, plan z następną płatnością, dane do faktury), dane profilu, bezpieczeństwo (zmiana hasła, wylogowanie wszędzie), skróty i wylogowanie. |
| `/shops/new` | `app/shops/new.tsx` | jw. Formularz nowego sklepu (na telefonie jako okno modalne). Bez planu zamiast formularza „Najpierw wybierz plan”. |
| `/billing` | `app/billing/index.tsx` | jw. Plan i płatności: stan planu, karta, anulowanie i wznowienie, dane do faktury, historia płatności. |
| `/billing/change` | `app/billing/change.tsx` | jw. Zmiana planu: podgląd dopłaty albo kwoty na saldo, wybór sklepów, które zostają aktywne, potwierdzenie. |
| `/billing/checkout` | `app/billing/checkout.tsx` | jw. Wybór planu, dane do faktury, zgody i przejście do płatności. |
| `/billing/return` | `app/billing/return.tsx` | jw. Powrót ze strony płatności (`?payment=<id>`): czeka na wynik i prowadzi do zakładania sklepu. |
| `/shops/[id]` | `app/shops/[id].tsx` | jw. Sklep: w trakcie zakładania postęp na paragonie; działający sklep ma kartę z przyciskami (sklep, ustawienia, panel WordPressa) na całą szerokość, pod nią „Ustawienia w skrócie” z kafelkami prowadzącymi do sekcji ustawień i paragon obok, dalej porady i usuwanie. W przeglądarce strzałka przy tytule cofa także po odświeżeniu strony (`backArrowOptions`). |
| `/shops/[id]/settings` | `app/shops/[id]/settings.tsx` | jw. Ustawienia działającego sklepu: menu sekcji i jedna wybrana sekcja (`?section=platnosci`), nowe hasło, usunięcie produktów przykładowych, ustawienia ręczne (logowanie do wp-admin), ostatnie zmiany. |

Dostęp do ekranów pilnuje `Stack.Protected` w [app/_layout.tsx](../mobile/src/app/_layout.tsx):
- niezalogowany trafia na stronę główną, zalogowany bez potwierdzonego e-maila na `/verify-email`;
- po zalogowaniu `/sign-in` przekierowuje na `/shops` (albo `/verify-email`).

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
  - Zwraca `{data, error, isLoading, isRefreshing, refresh}`.
- **[context/auth.tsx](../mobile/src/context/auth.tsx)** to `useAuth()`: `user`, `signIn`, `signUp`, `signOut`, `verifyEmail`, `resendCode`, `updateProfile`.
- **[context/notifications.tsx](../mobile/src/context/notifications.tsx)** to `useNotify()` z metodami `success(tekst)` i `error(tekst)`.
  - Pokazuje pasek na górze ekranu: zielony na 4 s albo czerwony na 7 s.
  - Wynik każdej operacji (zapis, wysłanie, usunięcie, błąd serwera) zgłaszaj przez ten pasek. Błędy konkretnych pól pokazuj pod polami.

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
| [constants/content.ts](../mobile/src/constants/content.ts) | Teksty strony głównej: kroki na paragonie, funkcje (slajdy), motywy, FAQ o sklepach (`Faq`) i o planach (`PricingFaq`, też w cenniku, „Jak to działa” i Pomocy). Liczby sklepów i ceny w odpowiedziach trzeba poprawić przy zmianie planów. |
| [constants/shop-guides.ts](../mobile/src/constants/shop-guides.ts) | Porady w szczegółach sklepu i w zakładce Pomoc |

Markiza (`Awning`) wygląda wszędzie tak samo: paski 40×16 px, liczba pasków zależy od szerokości, pierwszy zawsze zielony.
Kolor drugiego paska wybiera tylko `tone`, zależnie od tła pod spodem: `page` (domyślnie, zielony i biały),
`card` na białej karcie (zielony i jasnozielony), `green` na zielonym tle (jasnozielony i biały).
Strona `/docs/` rysuje ten sam wzór w SVG ([page.html](../backend/handbook/templates/handbook/page.html)).

Kolory pobieraj przez `useTheme()`, nie wpisuj ich na sztywno. Wyjątek to zdjęcia i podglądy.
Czcionki: Bricolage Grotesque w nagłówkach, Figtree w tekście, czcionka maszynowa tylko na paragonie.
Ikony: `Icon` z nazwami z listy w [components/icon.tsx](../mobile/src/components/icon.tsx).
Na iOS to symbole SF, na Androidzie i w przeglądarce Material Symbols.

Szerokie ekrany (od `WideBreakpoint` = 900 px) dostają układ w kolumnach.
Ruch na ekranie (Reanimated) respektuje systemowe ograniczenie ruchu.

## Najważniejsze komponenty

| Komponent | Do czego |
|---|---|
| `Page` | Przewijana strona z wyśrodkowaną treścią, opcjonalnym nagłówkiem i stopką na całą szerokość; dba o klawiaturę. `usePageScroll()` daje sekcjom pozycję przewinięcia. Na wąskich ekranach po przewinięciu o więcej niż ekran pokazuje okrągły przycisk, który od razu przenosi na górę strony (przyklejone sekcje przepuszczają ten skok). |
| `KeyboardArea` | Na Androidzie zmniejsza obszar, gdy otwiera się klawiatura (aplikacja zajmuje cały ekran, więc system tego nie robi) |
| `SiteHeader`, `SiteFooter` | Nagłówek i stopka stron publicznych w przeglądarce |
| `AuthLayout` | Układ logowania, rejestracji i potwierdzania e-maila |
| `ui/Button`, `ui/TextField`, `ui/ChipSelect`, `ui/SwitchRow`, `ui/Tooltip` | Podstawowe kontrolki. `SwitchRow` to ustawienie włącz/wyłącz z opisem; przełącza je cały wiersz. `Button` delikatnie powiększa się po najechaniu i zapada przy wciśnięciu. |
| `Receipt` | Paragon z wierszami, sumą i pieczątką; po najechaniu unosi się i obraca |
| `ShopSign`, `StatusBadge`, `TestBadge` | Karta sklepu na liście (sklepy zawieszone przez plan wyszarzone i na końcu listy), znacznik statusu i znacznik „Testowy” sklepów sprzed płatnych planów |
| `NewShopButton` | Przycisk nowego sklepu; bez planu prowadzi do wyboru planu, po osiągnięciu limitu planu wyszarzony z dymkiem. Sklepy testowe nie liczą się do limitu (`paidShopCount`). |
| `PlanCard`, `BillingProfileForm` | Plan z ceną brutto, korzyściami i znacznikiem „Polecany” (do wyboru albo z przyciskiem wyrównanym do dołu karty) i formularz danych do faktury (osoba albo firma z NIP) |
| `FeatureSlides` | „Co dostajesz” na całą szerokość pod markizą. Przy przewijaniu przyklejona witryna, w której każde przewinięcie pokazuje następny slajd (`PinnedSequence`); przy ograniczonym ruchu pokaz slajdów ze strzałkami, kropkami i automatycznym przewijaniem. Zdjęcia przechodzą po bokach gradientem w kolor strony (`SIDE_FADE_WIDE`, `SIDE_FADE_NARROW`). |
| `ThemeShowcase` | Motywy jako pasy na całą szerokość: zrzut sklepu przechodzący gradientem w tło. Przy przewijaniu działa jak `FeatureSlides` (`PinnedSequence`); przy ograniczonym ruchu zwykła lista. |
| `PinnedSequence`, `SwapLayer` | Wspólny mechanizm obu sekcji: przyklejenie nagłówka i sceny oraz podmiana elementu co około 160 px przewinięcia (`STEP`, `SWITCH_AT`). W przeglądarce przykleja CSS `sticky`. Na telefonie scena przesuwa się dokładnie o przewinięcie (położenie sekcji jest mierzone tylko przed przyklejeniem, więc nic nie drży), a jedno przesunięcie palcem zmienia najwyżej jeden element: rozpęd zatrzymuje się na następnym, a strona dociąga do pokazanego. `SwapLayer` to jedna warstwa sceny z przenikaniem. |
| `SettingsSection` | Karta jednej sekcji ustawień sklepu; po zmianie pokazuje „Zapisz” i „Cofnij”, każda sekcja zapisuje się osobno |
| `SettingsMenu`, `SettingsPane` | Menu sekcji ustawień: na szerokim ekranie lista z boku, na wąskim przewijany pasek nad treścią, z kropką przy sekcji z niezapisanymi zmianami. `SettingsPane` wsuwa nowo wybraną sekcję od strony ruchu w menu (z dołu lub góry obok listy, z boku pod paskiem). |
| `CtaBand` | Zielony pas z wezwaniem do działania na końcu strony |
| `FaqList` | Pytania i odpowiedzi; odpowiedź rozsuwa się płynnie, strzałka obraca się razem z nią, otwarte jest jedno pytanie naraz |
| `SectionHeader` | Tytuł i wstęp sekcji strony głównej (używany przez sekcje przyklejane) |
| `ShopLoginSteps`, `ShopGuidesPanel` | Kroki logowania do panelu WordPressa w „Ustawieniach ręcznych”: przycisk do panelu, adres, na który wysłano login i hasło, i „Wyślij dane ponownie”. Danych logowania aplikacja nie pokazuje. Obok porady jako slajdy. |
| `ShopOverview` | Kafelki ze stanem ustawień sklepu; brak płatności lub wysyłki jest wyróżniony (`missingForSales`), kafelek otwiera swoją sekcję ustawień |

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

Proporcje zdjęć są zapisane obok nich w `content.ts` (`aspectRatio`). W przeglądarce `Image`
nie dopasowuje się sam do proporcji, więc po podmianie zdjęcia trzeba je poprawić.

## Uruchamianie i sprawdzanie

```bash
npx expo start          # w: przeglądarka, kod QR: Expo Go
npx tsc --noEmit        # typy
npx expo lint           # lint (jeden znany błąd w szablonowym hooks/use-color-scheme.web.ts)
npm test                # testy (Jest z jest-expo i React Native Testing Library)
npm run test:coverage   # testy z pokryciem kodu; raport w coverage/lcov-report/index.html
```

Podgląd na telefonie: [uruchomienie.md](uruchomienie.md#podgląd-na-telefonie).

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

Testy sprawdzają to, co widzi użytkownik: szukają elementów po roli i nazwie (`getByRole('button', {name: 'Zapisz'})`),
nie po identyfikatorach. Dlatego pola formularzy mają `accessibilityLabel` z widocznej etykiety.
React Native Testing Library 14 renderuje asynchronicznie: `await render(...)` i `await fireEvent.press(...)`.

Atrapa `Link` zgłasza błąd, gdy element owinięty przez `asChild` dostaje tablicę stylów, tak jak prawdziwy
Expo Router. Taki element dostaje jeden obiekt stylów (`StyleSheet.flatten`); funkcji stylu `asChild` też nie przekazuje.

Nietestowane zostają głównie animacje strony głównej (przyklejane sekcje, pokaz slajdów), układy nawigacji
i pliki tylko dla przeglądarki.
