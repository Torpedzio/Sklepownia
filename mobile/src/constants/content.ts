/** Copy shared by several screens. */

import type { IconName } from '@/components/icon';

export const SetupSteps = [
  { label: 'Przydzielanie serwera', time: '0:01' },
  { label: 'Tworzenie bazy danych', time: '0:02' },
  { label: 'Uruchamianie WordPressa', time: '0:06' },
  { label: 'Instalacja WordPressa', time: '0:10' },
  { label: 'Ustawienia języka i regionu', time: '0:18' },
  { label: 'Konfiguracja WooCommerce', time: '0:52' },
  { label: 'Instalacja motywu', time: '0:58' },
  { label: 'Tworzenie kategorii', time: '1:21' },
  { label: 'Wyszukiwarka, kategorie i filtry', time: '1:35' },
  { label: 'Generowanie kluczy API', time: '1:39' },
  { label: 'Sprawdzanie działania sklepu', time: '1:45' },
];

export type Feature = {
  icon: IconName;
  title: string;
  text: string;
  /** Photo for the home page slideshow; features without one get a drawn slide. */
  image?: {
    source: number;
    /** Width divided by height of the file. */
    aspectRatio: number;
    /** Which side of the photo to keep when a narrow screen crops it. */
    focus?: 'left' | 'center' | 'right';
  };
  /** Set to false to list the feature on the about page only. */
  homeSlide?: boolean;
};

export const Features: Feature[] = [
  {
    icon: 'store',
    title: 'Sklep po polsku od pierwszej minuty',
    text: 'Złotówki, polska strefa czasowa, strony koszyka, zamówienia i konta klienta. Bez kreatora konfiguracji.',
    image: { source: require('@/assets/images/features/store.jpg'), aspectRatio: 850 / 569 },
  },
  {
    icon: 'category',
    title: 'Kategorie dopasowane do branży',
    text: 'Sprzedajesz ceramikę? Dostajesz kategorie dla ceramiki, nie „Kategoria 1”. Nazwy zmienisz w każdej chwili.',
    image: { source: require('@/assets/images/features/categories.jpg'), aspectRatio: 1408 / 768 },
  },
  {
    icon: 'filter',
    title: 'Wyszukiwarka i filtry',
    text: 'Klienci szukają produktów, przeglądają kategorie z boku i zawężają wyniki suwakiem ceny.',
    homeSlide: false,
  },
  {
    icon: 'palette',
    title: 'Trzy sprawdzone motywy',
    text: 'Storefront, Astra albo Kadence. Wybierasz przy zakładaniu, zmieniasz kiedy chcesz.',
    image: { source: require('@/assets/images/features/themes.jpg'), aspectRatio: 1600 / 900, focus: 'right' },
  },
  {
    icon: 'admin',
    title: 'Pełny panel WooCommerce',
    text: 'Produkty, zamówienia, płatności i wysyłka w panelu, którego używają miliony sklepów.',
  },
  {
    icon: 'shield',
    title: 'Każdy sklep osobno',
    text: 'Twój sklep ma własną bazę i własne środowisko. Kłopoty innych sklepów go nie dotyczą.',
    image: { source: require('@/assets/images/features/isolation.jpg'), aspectRatio: 1300 / 800 },
  },
];

export const Themes = [
  { name: 'Storefront', text: 'Klasyczny, czytelny, z wyszukiwarką w nagłówku.', colors: ['#333333', '#96588A', '#F8F8F8'] },
  { name: 'Astra', text: 'Lekki i szybki, z wyraźnymi przyciskami.', colors: ['#0170B9', '#1E293B', '#F1F5F9'] },
  { name: 'Kadence', text: 'Nowoczesny, z kartami produktów i dużymi nagłówkami.', colors: ['#2B6CB0', '#1A202C', '#EDF2F7'] },
];

export const Faq = [
  {
    question: 'Ile trwa założenie sklepu?',
    answer: 'Zwykle niecałe dwie minuty. Każdy krok widzisz na żywo w aplikacji, a gdy sklep jest gotowy, od razu możesz go otworzyć.',
  },
  {
    question: 'Na czym działa mój sklep?',
    answer: 'Na WordPressie z wtyczką WooCommerce, najpopularniejszym rozwiązaniu do sprzedaży w internecie. Dostajesz pełny panel administracyjny.',
  },
  {
    question: 'Jak dodać własne produkty?',
    answer: 'Otwórz panel sklepu z poziomu aplikacji i wybierz Produkty → Dodaj nowy. Kategorie są już przygotowane, a przykładowe produkty możesz usunąć.',
  },
  {
    question: 'Jak przyjmować płatności?',
    answer: 'W panelu sklepu przejdź do WooCommerce → Ustawienia → Płatności i włącz przelew, płatność przy odbiorze albo bramkę płatniczą.',
  },
  {
    question: 'Czy mogę zmienić wygląd sklepu później?',
    answer: 'Tak. W panelu sklepu, w sekcji Wygląd, zmienisz motyw, kolory, logo i menu.',
  },
  {
    question: 'Ile sklepów mogę założyć?',
    answer: 'Na jednym koncie możesz mieć do trzech sklepów jednocześnie. Usunięty sklep zwalnia miejsce.',
  },
  {
    question: 'Czy mogę podpiąć własną domenę?',
    answer: 'Jeszcze nie. Na razie sklep działa pod adresem w naszej domenie. Własne domeny są następne w kolejce.',
  },
  {
    question: 'Co, jeśli zakładanie się nie powiedzie?',
    answer: 'Na ekranie sklepu pojawi się przycisk „Spróbuj ponownie”. Zakładanie ruszy od miejsca, w którym się zatrzymało.',
  },
];
