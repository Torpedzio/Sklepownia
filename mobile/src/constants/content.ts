/** Copy shared by several screens. */

import type { IconName } from '@/components/icon';

export const SetupSteps = [
  { label: 'Miejsce na serwerze', time: '0:01' },
  { label: 'Baza produktów i zamówień', time: '0:02' },
  { label: 'Uruchomienie sklepu', time: '0:06' },
  { label: 'Strona i konto administratora', time: '0:10' },
  { label: 'Język i strefa czasowa', time: '0:18' },
  { label: 'Waluta, koszyk i zamówienia', time: '0:52' },
  { label: 'Wygląd sklepu', time: '0:58' },
  { label: 'Kategorie produktów', time: '1:21' },
  { label: 'Wyszukiwarka i filtry', time: '1:35' },
  { label: 'Połączenie z aplikacją', time: '1:39' },
  { label: 'Końcowe sprawdzenie', time: '1:45' },
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
    title: 'Twój sklep od pierwszej minuty',
    text: 'Język, waluta i strefa czasowa z formularza, gotowy koszyk, zamówienia i konta klientów. Bez kreatora konfiguracji.',
    image: { source: require('@/assets/images/features/store.jpg'), aspectRatio: 1264 / 846 },
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
    image: { source: require('@/assets/images/features/admin.jpg'), aspectRatio: 1385 / 880, focus: 'right' },
  },
  {
    icon: 'shield',
    title: 'Każdy sklep osobno',
    text: 'Twój sklep ma własną bazę i własne środowisko. Kłopoty innych sklepów go nie dotyczą.',
    image: { source: require('@/assets/images/features/isolation.jpg'), aspectRatio: 1300 / 800 },
  },
];

// Previews are screenshots of shops set up by the app, so they show what a new shop really looks like.
export const Themes = [
  {
    name: 'Storefront',
    text: 'Motyw od twórców WooCommerce. Klasyczny i czytelny: wyszukiwarka i koszyk w nagłówku, kategorie z boku.',
    colors: ['#333333', '#96588A', '#F8F8F8'],
    preview: require('@/assets/images/themes/storefront.jpg'),
  },
  {
    name: 'Astra',
    text: 'Lekki i szybki. Pod każdym produktem wyraźny przycisk „Dodaj do koszyka”, wyszukiwarka nad listą kategorii.',
    colors: ['#0170B9', '#1E293B', '#F1F5F9'],
    preview: require('@/assets/images/themes/astra.jpg'),
  },
  {
    name: 'Kadence',
    text: 'Nowoczesny, z kartami produktów i banerem nad listą. Klienci przełączają widok między siatką a listą.',
    colors: ['#2B6CB0', '#1A202C', '#EDF2F7'],
    preview: require('@/assets/images/themes/kadence.jpg'),
  },
];

/** Width divided by height of the theme preview screenshots. */
export const ThemePreviewAspectRatio = 1200 / 750;

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
