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
    text: 'WooCommerce z tysiącami wtyczek, PrestaShop popularny w Polsce albo Magento dla dużych katalogów (w planach Standard i Biznes). Wybierasz przy zakładaniu sklepu.',
    // The home page has a section of its own about the systems.
    homeSlide: false,
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

/** One band of a Showcase: a screenshot fading into the page, with a description next to it. */
export type ShowcaseItem = {
  name: string;
  /** Short line above the name. */
  label: string;
  text: string;
  /** Smaller line under the text. */
  details?: string;
  preview: number;
  /** What the screenshot shows, for screen readers. */
  alt: string;
};

// Previews are screenshots of shops set up by the app, so they show what a new shop really looks like.
export const Platforms: ShowcaseItem[] = [
  {
    name: 'WooCommerce',
    label: 'We wszystkich planach',
    text: 'WordPress z wtyczką sklepu. Najwięcej dodatków, motywów i poradników, a w aplikacji zmienisz w nim najwięcej ustawień. Dobry wybór na początek.',
    details: 'Motywy Storefront, Astra i Kadence. Sklep gotowy w około dwie minuty.',
    preview: require('@/assets/images/themes/storefront.jpg'),
    alt: 'Sklep WooCommerce z motywem Storefront',
  },
  {
    name: 'PrestaShop',
    label: 'We wszystkich planach',
    text: 'Samodzielny system sklepowy, popularny w Polsce. Rozbudowany katalog z wariantami produktów i wygodna obsługa zamówień.',
    details: 'Motywy Hummingbird i Classic. Sklep gotowy w około dwie minuty.',
    preview: require('@/assets/images/themes/hummingbird.jpg'),
    alt: 'Sklep PrestaShop z motywem Hummingbird',
  },
  {
    name: 'Magento',
    label: 'W planach Standard i Biznes',
    text: 'Dla większych sklepów: duży katalog, kilka magazynów i wersji językowych, porównywanie produktów i listy życzeń.',
    details: 'Motyw Luma. Sklep gotowy w około minutę.',
    preview: require('@/assets/images/themes/luma.jpg'),
    alt: 'Sklep Magento z motywem Luma',
  },
];

/** Width divided by height of the preview screenshots. */
export const PreviewAspectRatio = 1200 / 750;

/** Colours of every theme a shop can start with, for the swatches in the new shop form. */
export const ThemeColors: Record<string, string[]> = {
  Storefront: ['#333333', '#96588A', '#F8F8F8'],
  Astra: ['#0170B9', '#1E293B', '#F1F5F9'],
  Kadence: ['#2B6CB0', '#1A202C', '#EDF2F7'],
  Hummingbird: ['#0D6EFD', '#212529', '#F5F6F8'],
  Classic: ['#24B9D7', '#232323', '#F6F6F6'],
  Luma: ['#1979C3', '#333333', '#F0F0F0'],
};

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
      'Jeśli nie wiesz, wybierz WooCommerce. To WordPress z wtyczką sklepu: ma najwięcej wtyczek, motywów i poradników, a w aplikacji zmienisz w nim najwięcej ustawień. PrestaShop to samodzielny system sklepowy, popularny w Polsce, z rozbudowanym katalogiem i obsługą zamówień. Magento jest dla większych sklepów: z dużym katalogiem, kilkoma magazynami albo wersjami językowymi. Potrzebuje więcej zasobów serwera, dlatego jest w planach Standard (jeden sklep Magento) i Biznes (do pięciu).',
  },
  {
    question: 'Ile sklepów mogę założyć?',
    answer:
      'Tyle, ile pozwala Twój plan: Start to jeden sklep, Standard do trzech (w tym jeden na Magento), Biznes do dziesięciu (w tym do pięciu na Magento). Usunięty sklep zwalnia miejsce, a większy plan wybierzesz w każdej chwili.',
  },
  {
    question: 'Jak dodać własne produkty?',
    answer:
      'Otwórz panel sklepu z poziomu aplikacji. W WooCommerce wybierz Produkty → Dodaj nowy, w PrestaShop i Magento Katalog → Produkty. Kategorie są już przygotowane, a przykładowe produkty usuniesz jednym przyciskiem w ustawieniach sklepu.',
  },
  {
    question: 'Jak mój sklep przyjmie płatności od klientów?',
    answer:
      'Przelew i płatność przy odbiorze włączysz w aplikacji, w ustawieniach sklepu. Tam też podłączysz płatności online Przelewy24 i PayU (BLIK, szybkie przelewy, karty) w sklepie WooCommerce i PrestaShop, jeśli masz konto sprzedawcy u operatora. W sklepie Magento płatności online dodasz w panelu sklepu modułem operatora.',
  },
  {
    question: 'Skąd wziąć regulamin i politykę prywatności?',
    answer:
      'Przygotujemy je w aplikacji: w ustawieniach sklepu, w sekcji Regulamin, podajesz dane sprzedawcy i zasady zwrotów, a my publikujemy oba dokumenty jako strony sklepu. Płatności i dostawy bierzemy z ustawień, więc po każdej zmianie dokumenty aktualizują się same. Wzory są zgodne z polskim prawem, ale przy nietypowej sprzedaży, np. żywności czy usług, warto pokazać je prawnikowi.',
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
      'Tak, w każdej chwili w zakładce Plan i płatności, a data płatności się nie zmienia. Za wyższy plan dopłacasz tylko za dni do końca opłaconego okresu. Przy niższym niewykorzystana kwota pomniejszy kolejne płatności, a sklepy ponad limit planu (także sklepy Magento ponad jego limit) zostaną zawieszone. Nic z nich nie zniknie i przywrócisz je, gdy zrobi się miejsce.',
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
      'Tak, po każdej płatności. Przy wyborze planu podajesz dane do faktury: osoby prywatnej albo firmy z NIP-em. Fakturę wyślemy e-mailem, a wszystkie znajdziesz w zakładce Plan i płatności. Tam też zmienisz dane do kolejnych faktur.',
  },
];
