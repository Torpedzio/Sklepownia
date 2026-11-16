# Rozwój projektu

## Sprawdzanie zmian

Przed commitem:

```bash
docker compose exec backend pytest                                                      # testy backendu
docker compose exec backend python manage.py spectacular --validate --fail-on-warn > /dev/null   # schemat API
cd mobile && npx tsc --noEmit && npx expo lint && npm test                             # typy, lint i testy aplikacji
```

Lint aplikacji zgłasza jeden błąd w szablonowym pliku `mobile/src/hooks/use-color-scheme.web.ts`.

Pokrycie testami: `docker compose exec backend pytest --cov` i `cd mobile && npm run test:coverage`.
Nowa funkcja dostaje testy w tym samym commicie: backend w `*/tests/`, aplikacja w `__tests__`
(opis narzędzi: [backend.md](backend.md#testy), [aplikacja-mobilna.md](aplikacja-mobilna.md#testy)).

## Konwencje

- **Aplikacja:** formatowanie Prettierem z pojedynczymi cudzysłowami, liniami do 120 znaków
  i nawiasem zamykającym tag JSX w tej samej linii (`--single-quote --print-width 120 --bracket-same-line`).
  Pozostałe zasady: [mobile/README.md](../mobile/README.md#zasady).
- **Pakiety Expo** instaluj przez `npx expo install <pakiet>`, żeby wersja pasowała do SDK.
- **Teksty dla użytkownika** są po polsku i opisują rzeczy językiem użytkownika, nie nazwami technicznymi.
- **Sekrety** są tylko w plikach `.env`, które nie trafiają do repozytorium. Wzory z opisem zmiennych są w `.env.example`.

## Utrzymanie dokumentacji

Dokumentacja to zwykłe pliki Markdown w repozytorium i zmienia się razem z kodem, w tym samym commicie.

- Nowa zmienna środowiskowa: dopisz ją do [.env.example](../.env.example) z komentarzem i do tabeli w [uruchomienie.md](uruchomienie.md).
- Nowy endpoint: opisz go w [api.md](api.md). Pełny opis pól generuje się sam (`/api/docs/`) z serializerów i `@extend_schema`.
- Nowy krok zakładania sklepu: dopisz go do kroków platformy w [platforms/\_\_init\_\_.py](../backend/shops/platforms/__init__.py) i do tabeli w README platformy w [infra/shops/](../infra/shops/README.md).
- Nowy ekran albo komponent współdzielony: dopisz go do [aplikacja-mobilna.md](aplikacja-mobilna.md).
- Zrobiona pozycja z [ograniczenia-i-plan.md](ograniczenia-i-plan.md): usuń ją stamtąd.
- Nowy plik dokumentacji: dopisz go do tabeli w [README.md](../README.md) i do `PAGES`
  w [backend/handbook/pages.py](../backend/handbook/pages.py), żeby pojawił się w menu strony `/docs/`.
  Test `test_every_listed_page_exists_in_the_repository` pilnuje, żeby każda pozycja menu miała swój plik.
