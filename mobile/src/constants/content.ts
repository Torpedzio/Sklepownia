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
    icon: 'cart',
    title: 'Trzy systemy do wyboru',
    text: 'WooCommerce z tysiącami wtyczek, PrestaShop popularny w Polsce albo Magento dla dużych katalogów. Wybierasz przy zakładaniu sklepu.',
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
    text: 'Klienci szukają produktów, przeglądają kategorie i zawężają wyniki filtrem ceny.',
    homeSlide: false,
  },
  {
    icon: 'palette',
    title: 'Sprawdzone motywy',
    text: 'Storefront, Astra i Kadence w WooCommerce, Hummingbird i Classic w PrestaShop, Luma w Magento. Wybierasz przy zakładaniu.',
    image: { source: require('@/assets/images/features/themes.jpg'), aspectRatio: 1600 / 900, focus: 'right' },
  },
  {
    icon: 'admin',
    title: 'Pełny panel sklepu',
    text: 'Produkty, zamówienia, płatności i wysyłka w oryginalnym panelu WooCommerce, PrestaShop albo Magento.',
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
    platform: 'WooCommerce',
    text: 'Motyw od twórców WooCommerce. Klasyczny i czytelny: wyszukiwarka i koszyk w nagłówku, kategorie z boku.',
    colors: ['#333333', '#96588A', '#F8F8F8'],
    preview: require('@/assets/images/themes/storefront.jpg'),
  },
  {
    name: 'Astra',
    platform: 'WooCommerce',
    text: 'Lekki i szybki. Pod każdym produktem wyraźny przycisk „Dodaj do koszyka”, wyszukiwarka nad listą kategorii.',
    colors: ['#0170B9', '#1E293B', '#F1F5F9'],
    preview: require('@/assets/images/themes/astra.jpg'),
  },
  {
    name: 'Kadence',
    platform: 'WooCommerce',
    text: 'Nowoczesny, z kartami produktów i banerem nad listą. Klienci przełączają widok między siatką a listą.',
    colors: ['#2B6CB0', '#1A202C', '#EDF2F7'],
    preview: require('@/assets/images/themes/kadence.jpg'),
  },
  {
    name: 'Hummingbird',
    platform: 'PrestaShop',
    text: 'Nowy motyw PrestaShop 9. Kategorie w menu i obok listy, filtry ceny i dostępności, koszyk przy każdym produkcie.',
    colors: ['#0D6EFD', '#212529', '#F5F6F8'],
    preview: require('@/assets/images/themes/hummingbird.jpg'),
  },
  {
    name: 'Luma',
    platform: 'Magento',
    text: 'Motyw Magento z kategoriami w menu, filtrami obok listy, porównywaniem produktów i listą życzeń.',
    colors: ['#1979C3', '#333333', '#F0F0F0'],
    preview: require('@/assets/images/themes/luma.jpg'),
  },
];

/** Colours of every theme a shop can start with, for the swatches in the new shop form. */
export const ThemeColors: Record<string, string[]> = {
  ...Object.fromEntries(Themes.map((theme) => [theme.name, theme.colors])),
  // PrestaShop's older theme, without a preview on the home page.
  Classic: ['#24B9D7', '#232323', '#F6F6F6'],
};

/** Width divided by height of the theme preview screenshots. */
export const ThemePreviewAspectRatio = 1200 / 750;

/** About the shops themselves; plans and payments are in PricingFaq. */
export const Faq = [
  {
    question: 'Ile trwa założenie sklepu?',
    answer:
      'Od minuty do dwóch, zależnie od systemu sklepu. Każdy krok widzisz na żywo w aplikacji, a gdy sklep jest gotowy, od razu możesz go otworzyć.',
  },
  {
    question: 'Na czym działa mój sklep?',
    answer:
      'Na systemie, który wybierzesz przy zakładaniu: WooCommerce, PrestaShop albo Magento. Każdy sklep ma pełny panel administracyjny, a login i hasło do niego przychodzą e-mailem. Systemu nie zmienisz po założeniu sklepu.',
  },
  {
    question: 'Który system wybrać?',
    answer:
      'Jeśli nie wiesz, wybierz WooCommerce. To WordPress z wtyczką sklepu: ma najwięcej wtyczek, motywów i poradników, a w aplikacji zmienisz w nim najwięcej ustawień. PrestaShop to samodzielny system sklepowy, popularny w Polsce, z rozbudowanym katalogiem i obsługą zamówień. Magento jest dla większych sklepów: z dużym katalogiem, kilkoma magazynami albo wersjami językowymi.',
  },
  {
    question: 'Ile sklepów mogę założyć?',
    answer:
      'Tyle, ile pozwala Twój plan: Start to jeden sklep, Standard do trzech, Biznes do dziesięciu. Usunięty sklep zwalnia miejsce, a większy plan wybierzesz w każdej chwili.',
  },
  {
    question: 'Jak dodać własne produkty?',
    answer:
      'Otwórz panel sklepu z poziomu aplikacji. W WooCommerce wybierz Produkty → Dodaj nowy, w PrestaShop i Magento Katalog → Produkty. Kategorie są już przygotowane, a przykładowe produkty usuniesz jednym przyciskiem w ustawieniach sklepu.',
  },
  {
    question: 'Jak mój sklep przyjmie płatności od klientów?',
    answer:
      'Przelew i płatność przy odbiorze włączysz w aplikacji, w ustawieniach sklepu. Płatności online, np. BLIK i karty, dodasz w panelu sklepu wtyczką albo modułem wybranego operatora.',
  },
  {
    question: 'Czy mogę zmienić wygląd sklepu później?',
    answer:
      'Tak. Motyw sklepu WooCommerce i PrestaShop zmienisz w aplikacji, w ustawieniach sklepu. Kolory, logo i menu ustawisz w panelu sklepu, tak samo jak wygląd sklepu Magento.',
  },
  {
    question: 'Czy mogę podpiąć własną domenę?',
    answer: 'Jeszcze nie. Na razie sklep działa pod adresem w naszej domenie. Własne domeny są następne w kolejce.',
  },
  {
    question: 'Co, jeśli zakładanie się nie powiedzie?',
    answer:
      'Na ekranie sklepu pojawi się przycisk „Spróbuj ponownie”. Zakładanie ruszy od miejsca, w którym się zatrzymało.',
  },
];

/** Plans and paying for them: on the pricing page, and after the shop questions elsewhere. */
export const PricingFaq = [
  {
    question: 'Ile to kosztuje?',
    answer:
      'Od 29 do 99 zł miesięcznie, zależnie od planu. Ceny zawierają VAT. W cenie są serwer, aktualizacje i pomoc, bez dodatkowych opłat za zakładanie sklepów.',
  },
  {
    question: 'Jak płacę za plan?',
    answer:
      'Kartą, przez Tpay. Dane karty wpisujesz na stronie operatora, więc do nas nie trafiają. Kolejne płatności pobierają się same co miesiąc z zapisanej karty, a potwierdzenie każdej dostajesz e-mailem.',
  },
  {
    question: 'Czy mogę zmienić plan?',
    answer:
      'Tak, w każdej chwili w zakładce Plan i płatności, a data płatności się nie zmienia. Za wyższy plan dopłacasz tylko za dni do końca opłaconego okresu. Przy niższym niewykorzystana kwota pomniejszy kolejne płatności, a sklepy ponad limit planu zostaną zawieszone. Nic z nich nie zniknie i przywrócisz je, gdy zrobi się miejsce.',
  },
  {
    question: 'Jak zrezygnować?',
    answer:
      'Anulujesz plan jednym przyciskiem w zakładce Plan i płatności. Działa do końca opłaconego okresu i nie pobierzemy już kolejnej płatności. Zmienisz zdanie przed końcem okresu? Wznowisz go tam samo.',
  },
  {
    question: 'Co, jeśli płatność się nie uda?',
    answer:
      'Spróbujemy ponownie po jednym, trzech i pięciu dniach i za każdym razem napiszemy e-mail. Jeśli żadna próba się nie uda, plan wygaśnie, a nowe sklepy założysz dopiero po wybraniu planu.',
  },
  {
    question: 'Czy dostanę fakturę?',
    answer:
      'Tak. Przy wyborze planu podajesz dane do faktury: osoby prywatnej albo firmy z NIP-em. Zmienisz je później w zakładce Plan i płatności.',
  },
];
