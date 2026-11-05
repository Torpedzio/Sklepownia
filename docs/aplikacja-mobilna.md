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
| `/` | `app/index.tsx` | Wszyscy. Strona główna z pokazem slajdów, krokami, motywami i FAQ. |
| `/about` | `app/about.tsx` | Wszyscy. „Jak to działa”, cała lista funkcji i pytań. |
| `/contact` | `app/contact.tsx` | Wszyscy. Dane kontaktowe i formularz. |
| `/sign-in`, `/sign-up` | `app/sign-in.tsx`, `app/sign-up.tsx` | Tylko niezalogowani |
| `/verify-email` | `app/verify-email.tsx` | Zalogowani bez potwierdzonego e-maila |
| `/shops` | `app/(tabs)/shops.tsx` | Zalogowani z potwierdzonym e-mailem. Lista sklepów. |
| `/help` | `app/(tabs)/help.tsx` | jw. Porady dotyczące prowadzenia sklepu. |
| `/account` | `app/(tabs)/account.tsx` | jw. Profil i wylogowanie. |
| `/shops/new` | `app/shops/new.tsx` | jw. Formularz nowego sklepu (na telefonie jako okno modalne). |
| `/shops/[id]` | `app/shops/[id].tsx` | jw. Szczegóły: postęp, dostęp do panelu, porady, usuwanie. |

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
| [constants/content.ts](../mobile/src/constants/content.ts) | Teksty strony głównej: kroki na paragonie, funkcje (slajdy), motywy, FAQ |
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
| `ui/Button`, `ui/TextField`, `ui/ChipSelect`, `ui/Tooltip` | Podstawowe kontrolki. `Button` delikatnie powiększa się po najechaniu i zapada przy wciśnięciu. |
| `Receipt` | Paragon z wierszami, sumą i pieczątką; po najechaniu unosi się i obraca |
| `ShopSign`, `StatusBadge` | Karta sklepu na liście i znacznik statusu |
| `NewShopButton` | Przycisk nowego sklepu; po osiągnięciu limitu wyszarzony, z dymkiem wyjaśnienia |
| `FeatureSlides` | „Co dostajesz” na całą szerokość pod markizą. Przy przewijaniu przyklejona witryna, w której każde przewinięcie pokazuje następny slajd (`PinnedSequence`); przy ograniczonym ruchu pokaz slajdów ze strzałkami, kropkami i automatycznym przewijaniem. Zdjęcia przechodzą po bokach gradientem w kolor strony (`SIDE_FADE_WIDE`, `SIDE_FADE_NARROW`). |
| `ThemeShowcase` | Motywy jako pasy na całą szerokość: zrzut sklepu przechodzący gradientem w tło. Przy przewijaniu działa jak `FeatureSlides` (`PinnedSequence`); przy ograniczonym ruchu zwykła lista. |
| `PinnedSequence`, `SwapLayer` | Wspólny mechanizm obu sekcji: przyklejenie nagłówka i sceny oraz podmiana elementu co około 160 px przewinięcia (`STEP`, `SWITCH_AT`). W przeglądarce przykleja CSS `sticky`. Na telefonie scena przesuwa się dokładnie o przewinięcie (położenie sekcji jest mierzone tylko przed przyklejeniem, więc nic nie drży), a jedno przesunięcie palcem zmienia najwyżej jeden element: rozpęd zatrzymuje się na następnym, a strona dociąga do pokazanego. `SwapLayer` to jedna warstwa sceny z przenikaniem. |
| `CtaBand` | Zielony pas z wezwaniem do działania na końcu strony |
| `FaqList` | Pytania i odpowiedzi; odpowiedź rozsuwa się płynnie, strzałka obraca się razem z nią, otwarte jest jedno pytanie naraz |
| `SectionHeader` | Tytuł i wstęp sekcji strony głównej (używany przez sekcje przyklejane) |
| `ShopLoginGuide`, `ShopGuidesPanel` | Instrukcja logowania do panelu WordPressa i porady jako slajdy |

Hook `useFullBleed` pozwala sekcji wyjść z wyśrodkowanej kolumny na całą szerokość strony.

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
```

Testów automatycznych aplikacja jeszcze nie ma. Podgląd na telefonie: [uruchomienie.md](uruchomienie.md#podgląd-na-telefonie).
