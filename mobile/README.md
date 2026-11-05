# Aplikacja mobilna

Aplikacja Sklepowni na iOS, Androida i przeglądarkę: strony publiczne, konto, zakładanie sklepów,
postęp zakładania, dostęp do panelu sklepu i porady. Expo SDK 58, React Native 0.88, Expo Router.

Pełny opis (ekrany, nawigacja, komponenty, wygląd, komunikacja z API):
[docs/aplikacja-mobilna.md](../docs/aplikacja-mobilna.md).

## Uruchomienie

Najpierw backend (z katalogu głównego: `docker compose up -d`), potem:

```bash
npm install
npx expo start
```

- `w` albo http://localhost:8081: wersja w przeglądarce
- kod QR: Expo Go na telefonie w tej samej sieci Wi-Fi ([podgląd na telefonie](../docs/uruchomienie.md#podgląd-na-telefonie))

Aplikacja łączy się z API pod `http://<host Metro>:8000/api`. Inny adres: zmienna `EXPO_PUBLIC_API_URL`.

## Sprawdzanie

```bash
npx tsc --noEmit
npx expo lint
npm test                # albo npm run test:coverage
```

## Zasady

- Pakiety instaluj przez `npx expo install`, nie `npm install <pakiet>`.
- W `src/app/` są tylko ekrany; komponenty, hooki i narzędzia trzymaj poza tym katalogiem.
- Kolory, odstępy i czcionki bierz z `src/constants/theme.ts` (`useTheme()`), teksty strony głównej z `src/constants/content.ts`.
- Wynik operacji pokazuj paskiem powiadomień (`useNotify()`), błędy pól pod polami formularza.

Wskazówki dla asystentów AI są w [AGENTS.md](AGENTS.md).
