/** Tips for running a WooCommerce shop. `adminPath` is relative to the shop's /wp-admin/. */

import type { IconName } from '@/components/icon';

export type ShopTip = {
  title: string;
  text: string;
  /** Where to click in the shop's admin panel. */
  menu: string;
  adminPath: string;
};

export type ShopGuide = {
  key: string;
  label: string;
  icon: IconName;
  intro: string;
  /** Steps meant to be done in this order, shown numbered. */
  ordered: boolean;
  tips: ShopTip[];
};

export const ShopGuides: ShopGuide[] = [
  {
    key: 'start',
    label: 'Pierwsze kroki',
    icon: 'store',
    intro: 'Zrób te rzeczy po kolei, zanim pokażesz sklep klientom.',
    ordered: true,
    tips: [
      {
        title: 'Uzupełnij dane firmy',
        text: 'Adres sklepu trafia na faktury i do wiadomości dla klientów. Sprawdź też walutę i kraje, do których sprzedajesz.',
        menu: 'WooCommerce → Ustawienia → Ogólne',
        adminPath: 'admin.php?page=wc-settings&tab=general',
      },
      {
        title: 'Dodaj logo i kolory',
        text: 'W Tożsamości witryny wgrasz logo i ikonę. Zmiany widzisz od razu w podglądzie, a zapisujesz przyciskiem Opublikuj.',
        menu: 'Wygląd → Dostosuj',
        adminPath: 'customize.php',
      },
      {
        title: 'Dodaj swoje produkty',
        text: 'Nazwa, cena, zdjęcie i kategoria wystarczą na start. Zdjęcia najlepiej kwadratowe, co najmniej 800 × 800 px.',
        menu: 'Produkty → Utwórz produkt',
        adminPath: 'post-new.php?post_type=product',
      },
      {
        title: 'Usuń przykładowe produkty',
        text: 'Zaznacz „Przykładowy produkt 1–6” na liście i wybierz Przenieś do kosza.',
        menu: 'Produkty → Wszystkie produkty',
        adminPath: 'edit.php?post_type=product',
      },
      {
        title: 'Włącz płatności',
        text: 'Przelew, płatność przy odbiorze, Przelewy24 i PayU włączysz w aplikacji. Tu ustawisz kolejność metod przy zamówieniu i innych operatorów płatności.',
        menu: 'WooCommerce → Ustawienia → Płatności',
        adminPath: 'admin.php?page=wc-settings&tab=checkout',
      },
      {
        title: 'Ustaw wysyłkę',
        text: 'Dodaj strefę „Polska” i metody dostawy z cenami, np. kurier i odbiór osobisty. Paczkomaty InPost dodasz ich wtyczką.',
        menu: 'WooCommerce → Ustawienia → Wysyłka',
        adminPath: 'admin.php?page=wc-settings&tab=shipping',
      },
      {
        title: 'Sprawdź regulamin i politykę prywatności',
        text: 'Oba dokumenty przygotujesz w aplikacji, w ustawieniach sklepu w sekcji Regulamin. Jeśli masz własne strony od prawnika, wskaż tu stronę regulaminu, a politykę prywatności w Ustawieniach → Prywatność.',
        menu: 'WooCommerce → Ustawienia → Zaawansowane',
        adminPath: 'admin.php?page=wc-settings&tab=advanced',
      },
      {
        title: 'Złóż zamówienie testowe',
        text: 'Kup coś we własnym sklepie, płacąc przelewem. Sprawdź koszyk, formularz zamówienia i to, czy zamówienie pojawiło się w panelu.',
        menu: 'WooCommerce → Zamówienia',
        adminPath: 'admin.php?page=wc-orders',
      },
    ],
  },
  {
    key: 'sell',
    label: 'Sprzedaż',
    icon: 'filter',
    intro: 'Kiedy sklep działa, te rzeczy pomogą sprzedawać więcej.',
    ordered: false,
    tips: [
      {
        title: 'Pozwól Google znaleźć sklep',
        text: 'Upewnij się, że opcja „Proś wyszukiwarki o nieindeksowanie” jest odznaczona. Potem dodaj sklep do Google Search Console.',
        menu: 'Ustawienia → Czytanie',
        adminPath: 'options-reading.php',
      },
      {
        title: 'Kody rabatowe',
        text: 'Utwórz kupon na procent albo kwotę, z datą ważności i limitem użyć. Dobry pomysł na pierwsze zamówienie albo newsletter.',
        menu: 'Marketing → Kupony',
        adminPath: 'edit.php?post_type=shop_coupon',
      },
      {
        title: 'Opinie klientów',
        text: 'Opinie są domyślnie włączone. Gdy produkty dostaną pierwsze oceny, w pasku bocznym sklepu pojawi się filtr ocen.',
        menu: 'WooCommerce → Ustawienia → Produkty',
        adminPath: 'admin.php?page=wc-settings&tab=products',
      },
      {
        title: 'Uporządkuj kategorie',
        text: 'Kategorie z menu w pasku bocznym zmienisz tutaj. Pusta kategoria pokazuje (0), więc dodaj do niej produkty albo ją usuń.',
        menu: 'Produkty → Kategorie',
        adminPath: 'edit-tags.php?taxonomy=product_cat&post_type=product',
      },
    ],
  },
  {
    key: 'manage',
    label: 'Zarządzanie',
    icon: 'admin',
    intro: 'Codzienna obsługa sklepu: zamówienia, magazyn i ludzie.',
    ordered: false,
    tips: [
      {
        title: 'Obsługa zamówień',
        text: 'Nowe opłacone zamówienie ma status „W trakcie realizacji”. Po wysłaniu paczki zmień go na „Zrealizowane”, a klient dostanie wiadomość.',
        menu: 'WooCommerce → Zamówienia',
        adminPath: 'admin.php?page=wc-orders',
      },
      {
        title: 'Stany magazynowe',
        text: 'Włącz zarządzanie magazynem i próg niskiego stanu. W każdym produkcie, w zakładce Magazyn, wpiszesz liczbę sztuk.',
        menu: 'WooCommerce → Ustawienia → Produkty → Magazyn',
        adminPath: 'admin.php?page=wc-settings&tab=products&section=inventory',
      },
      {
        title: 'Wiadomości do klientów',
        text: 'Zmień nazwę nadawcy, stopkę i treść e-maili o zamówieniu, wysyłce i zwrocie. Adres nadawcy ustawia platforma, a odpowiedzi klientów trafiają na adres kontaktowy sklepu.',
        menu: 'WooCommerce → Ustawienia → E-maile',
        adminPath: 'admin.php?page=wc-settings&tab=email',
      },
      {
        title: 'Sprzedaż i statystyki',
        text: 'Przychody, liczba zamówień i najlepiej sprzedające się produkty w wybranym okresie.',
        menu: 'Analityka → Przegląd',
        adminPath: 'admin.php?page=wc-admin&path=/analytics/overview',
      },
      {
        title: 'Konto dla pracownika',
        text: 'Dodaj osobę z rolą „Kierownik sklepu”. Obsłuży zamówienia i produkty, ale nie zmieni ustawień WordPressa.',
        menu: 'Użytkownicy → Dodaj użytkownika',
        adminPath: 'user-new.php',
      },
    ],
  },
];
