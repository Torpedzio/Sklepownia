/**
 * Menu names are the Polish ones of each admin panel: WordPress and WooCommerce, PrestaShop 9 (its Polish
 * language pack) and Magento (community-engineering/language-pl_pl).
 */

import type { IconName } from '@/components/icon';
import type { Platform } from '@/lib/types';

export type ShopTip = {
  title: string;
  text: string;
  menu: string;
  /** Relative to the panel (WooCommerce: /wp-admin/). PrestaShop/Magento pages need a session key, so they have none. */
  adminPath?: string;
};

export type ShopGuide = {
  key: string;
  label: string;
  icon: IconName;
  intro: string;
  /** Shown numbered, to be done in this order. */
  ordered: boolean;
  tips: ShopTip[];
};

const WooCommerceGuides: ShopGuide[] = [
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

const PrestaShopGuides: ShopGuide[] = [
  {
    key: 'start',
    label: 'Pierwsze kroki',
    icon: 'store',
    intro: 'Zrób te rzeczy po kolei, zanim pokażesz sklep klientom.',
    ordered: true,
    tips: [
      {
        title: 'Uzupełnij dane firmy',
        text: 'Na dole strony, w Danych kontaktowych, wpisz nazwę, adres, telefon i e-mail sklepu. Trafią do stopki sklepu i do wiadomości dla klientów.',
        menu: 'Preferencje → Kontakt → Sklepy',
      },
      {
        title: 'Dodaj logo',
        text: 'W sekcji Logo wgrasz logo nagłówka, logo do e-maili i faktur oraz ikonę strony (favicon).',
        menu: 'Wygląd → Szablony',
      },
      {
        title: 'Dodaj swoje produkty',
        text: 'Nazwa, cena, zdjęcie, ilość i kategoria wystarczą na start. Warianty, np. rozmiary i kolory, dodasz w produkcie jako kombinacje.',
        menu: 'Katalog → Produkty → Dodaj nowy produkt',
      },
      {
        title: 'Usuń przykładowe produkty',
        text: 'Najszybciej zrobisz to w aplikacji: Ustawienia sklepu → Bezpieczeństwo. W panelu zaznacz je na liście i wybierz Działania masowe → Usuń zaznaczone.',
        menu: 'Katalog → Produkty',
      },
      {
        title: 'Włącz płatności',
        text: 'Przelew, płatność przy odbiorze, Przelewy24 i PayU włączysz w aplikacji. Tu ustawisz, w jakich walutach i krajach oraz przy których przewoźnikach są dostępne.',
        menu: 'Płatność → Preferencje',
      },
      {
        title: 'Ustaw wysyłkę',
        text: 'Na start sklep ma tylko odbiór w sklepie („Click and collect”). Dodaj nowego przewoźnika, np. kuriera z ceną dla strefy Europe, w której jest Polska. Paczkomaty InPost dodasz ich modułem.',
        menu: 'Wysyłka → Przewoźnicy',
      },
      {
        title: 'Sprawdź regulamin',
        text: 'Regulamin i politykę prywatności przygotujesz w aplikacji, w sekcji Regulamin, a zgodę na regulamin przy zamówieniu włączymy sami. Własną stronę regulaminu wskażesz tu, w Warunkach korzystania z usługi.',
        menu: 'Preferencje → Zamówienia',
      },
      {
        title: 'Złóż zamówienie testowe',
        text: 'Kup coś we własnym sklepie, płacąc przelewem. Sprawdź koszyk, formularz zamówienia i to, czy zamówienie pojawiło się w panelu.',
        menu: 'Zamówienia → Zamówienia',
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
        text: 'Przy module Mapa strony Google wybierz Konfiguruj, a potem Generuj plik mapy strony. Jej adres dodasz w Google Search Console.',
        menu: 'Moduły → Menedżer modułów',
      },
      {
        title: 'Kody rabatowe',
        text: 'W Regułach koszyka dodaj kod: rabat procentowy albo kwotowy, daty ważności i limit użyć. Dobry pomysł na pierwsze zamówienie albo newsletter.',
        menu: 'Katalog → Rabaty',
      },
      {
        title: 'Opinie klientów',
        text: 'Opinie obsługuje moduł Komentarze produktu. Nowa opinia czeka na Twoje zatwierdzenie: znajdziesz ją po wybraniu Konfiguruj przy module.',
        menu: 'Moduły → Menedżer modułów',
      },
      {
        title: 'Uporządkuj kategorie',
        text: 'Kategorie z menu sklepu zmienisz tutaj. Kolejność ustawisz, przeciągając je na liście.',
        menu: 'Katalog → Kategorie',
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
        text: 'Gdy pieniądze za przelew dotrą, zmień status na „Płatność zaakceptowana”, a po nadaniu paczki na „Dostarczane” i dodaj numer przesyłki. Klient dostaje e-mail przy każdej zmianie.',
        menu: 'Zamówienia → Zamówienia',
      },
      {
        title: 'Stany magazynowe',
        text: 'Tu zmienisz liczbę sztuk wielu produktów naraz. Gdy produktu zostanie mało, dostaniesz e-mail.',
        menu: 'Katalog → Magazyn',
      },
      {
        title: 'Wiadomości do klientów',
        text: 'Wybierz wygląd e-maili i podejrzyj wiadomości o zamówieniu i wysyłce. Ich treść zmienisz w Międzynarodowe → Tłumaczenia. Adres nadawcy ustawia platforma.',
        menu: 'Wygląd → Motyw E-maila',
      },
      {
        title: 'Sprzedaż i statystyki',
        text: 'Sprzedaż, najczęściej kupowane produkty i odwiedziny w wybranym okresie. Najważniejsze liczby masz też w aplikacji, na ekranie sprzedaży sklepu.',
        menu: 'Statystyki',
      },
      {
        title: 'Konto dla pracownika',
        text: 'W zakładce Roles dodaj rolę i w Uprawnieniach zaznacz, co może robić, np. zamówienia i produkty. Potem dodaj pracownika z tą rolą.',
        menu: 'Zaawansowane → Zespół',
      },
    ],
  },
];

const MagentoGuides: ShopGuide[] = [
  {
    key: 'start',
    label: 'Pierwsze kroki',
    icon: 'store',
    intro: 'Zrób te rzeczy po kolei, zanim pokażesz sklep klientom.',
    ordered: true,
    tips: [
      {
        title: 'Uzupełnij dane firmy',
        text: 'Nazwa sklepu, telefon, adres i numer VAT trafiają do wiadomości dla klientów. Zmiany zapisujesz przyciskiem Zapisz konfigurację.',
        menu: 'Sklepy → Konfiguracja → Ogólne → Informacje o sklepie',
      },
      {
        title: 'Dodaj logo',
        text: 'Przy widoku sklepu wybierz Edytuj i w sekcji Nagłówek wgraj obrazek logo. W Nagłówku HTML ustawisz ikonkę witryny i tytuł strony.',
        menu: 'Zawartość → Wygląd → Konfiguracja',
      },
      {
        title: 'Dodaj swoje produkty',
        text: 'Nazwa, cena, ilość, zdjęcie i kategoria wystarczą na start. Produkt bez sztuk na stanie nie pojawi się w sklepie.',
        menu: 'Katalog → Produkty → Dodaj produkt',
      },
      {
        title: 'Usuń przykładowe produkty',
        text: 'Najszybciej zrobisz to w aplikacji: Ustawienia sklepu → Bezpieczeństwo. W panelu zaznacz je na liście i wybierz Działania → Usuń.',
        menu: 'Katalog → Produkty',
      },
      {
        title: 'Włącz płatności',
        text: 'Przelew i płatność przy odbiorze włączysz w aplikacji. Tu zmienisz ich nazwy, kolejność i kraje, w których są dostępne, a jeśli masz konto firmowe PayPal, podłączysz PayPal.',
        menu: 'Sklepy → Konfiguracja → Sprzedaż → Metody płatności',
      },
      {
        title: 'Sprawdź wysyłkę',
        text: 'Kuriera, darmową dostawę i odbiór osobisty ustawisz w aplikacji. Tu zmienisz nazwy metod i kraje, do których wysyłasz.',
        menu: 'Sklepy → Konfiguracja → Sprzedaż → Delivery Methods',
      },
      {
        title: 'Sprawdź regulamin',
        text: 'Regulamin i politykę prywatności przygotujesz w aplikacji, w sekcji Regulamin, a zgodę na regulamin przy zamówieniu dodamy sami. Tu zmienisz jej treść.',
        menu: 'Sklepy → Zasady składania zamówień',
      },
      {
        title: 'Złóż zamówienie testowe',
        text: 'Kup coś we własnym sklepie, płacąc przelewem. Sprawdź koszyk, formularz zamówienia i to, czy zamówienie pojawiło się w panelu.',
        menu: 'Sprzedaż → Zamówienia',
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
        text: 'Przy widoku sklepu wybierz Edytuj i sprawdź, czy Domyślne roboty to INDEX, FOLLOW. Mapę witryny dla Google Search Console dodasz w Marketing → SEO i wyszukiwanie → Mapa witryny.',
        menu: 'Zawartość → Wygląd → Konfiguracja',
      },
      {
        title: 'Kody rabatowe',
        text: 'Dodaj regułę z kuponem: rabat procentowy albo kwotowy, daty ważności i limit użyć. Dobry pomysł na pierwsze zamówienie albo newsletter.',
        menu: 'Marketing → Reguły cenowe koszyka',
      },
      {
        title: 'Opinie klientów',
        text: 'Nowa opinia czeka na Twoje zatwierdzenie. Zmień jej status na Zatwierdzony, a pojawi się przy produkcie.',
        menu: 'Marketing → Niezatwierdzone opinie',
      },
      {
        title: 'Uporządkuj kategorie',
        text: 'Kategorie z menu sklepu zmienisz tutaj. Kolejność ustawisz, przeciągając je na drzewie kategorii.',
        menu: 'Katalog → Kategorie',
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
        text: 'Gdy klient zapłaci, wybierz w zamówieniu Faktura, a po nadaniu paczki Dostawa z numerem przesyłki. Klient dostanie e-mail. Faktura z Magento nie jest fakturą VAT.',
        menu: 'Sprzedaż → Zamówienia',
      },
      {
        title: 'Stany magazynowe',
        text: 'Liczbę sztuk wpisujesz w każdym produkcie, w polu Ilość. Kończące się produkty pokaże raport Raporty → Produkty → Mało produktów.',
        menu: 'Sklepy → Konfiguracja → Katalog → Magazyn',
      },
      {
        title: 'Wiadomości do klientów',
        text: 'Dodaj własny szablon na bazie domyślnego, np. potwierdzenia zamówienia, a potem wskaż go w konfiguracji, w E-mailach sprzedażowych. Adres nadawcy ustawia platforma.',
        menu: 'Marketing → Szablony e-mail',
      },
      {
        title: 'Sprzedaż i statystyki',
        text: 'Przychód i liczba zamówień w wybranym okresie. Magento liczy raporty raz na dobę, a od razu przeliczysz je w Raporty → Statystyki → Odśwież statystyki.',
        menu: 'Raporty → Sprzedaż → Zamówienia',
      },
      {
        title: 'Konto dla pracownika',
        text: 'Najpierw w Role użytkownika dodaj rolę z dostępem do zamówień i produktów, a potem dodaj użytkownika z tą rolą.',
        menu: 'System → Lista użytkowników',
      },
    ],
  },
];

export const ShopGuides: Record<Platform, ShopGuide[]> = {
  woocommerce: WooCommerceGuides,
  prestashop: PrestaShopGuides,
  magento: MagentoGuides,
};
