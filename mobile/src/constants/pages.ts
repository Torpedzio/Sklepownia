import { Brand } from '@/constants/brand';

/** Pages anyone can open; the server renders them without the account check, for search engines and link previews. */
export type PublicPage = {
  path: string;
  /** Followed by the site's name (the home page has a full title). */
  title: string;
  description: string;
  /** In sitemap.xml and open to search engines; sign-in forms are not. */
  indexed: boolean;
};

export const HomeTitle = `${Brand.name}: sklep internetowy w dwie minuty`;

export const PublicPages: PublicPage[] = [
  {
    path: '/',
    title: HomeTitle,
    description:
      'Sklep internetowy na WooCommerce, PrestaShop albo Magento, otwarty w dwie minuty: z kategoriami, wyszukiwarką ' +
      'i panelem. Serwer i aktualizacje są po naszej stronie.',
    indexed: true,
  },
  {
    path: '/about',
    title: 'Jak to działa',
    description:
      'Opisujesz sklep w krótkim formularzu, a my zakładamy go na serwerze: system, motyw, kategorie i wyszukiwarka. ' +
      'Zobacz, co dostajesz i jak przebiega zakładanie.',
    indexed: true,
  },
  {
    path: '/pricing',
    title: 'Cennik',
    description:
      'Plany z cenami brutto: sklepy, serwer, aktualizacje i pomoc w jednej opłacie. Płacisz kartą co miesiąc, ' +
      'a plan zmieniasz albo anulujesz w każdej chwili.',
    indexed: true,
  },
  {
    path: '/contact',
    title: 'Kontakt',
    description: `Pytania o zakładanie sklepu, plany albo płatności? Napisz do nas albo zadzwoń: ${Brand.contact.hours.toLowerCase()}.`,
    indexed: true,
  },
  {
    path: '/sign-in',
    title: 'Logowanie',
    description: 'Zaloguj się, żeby zarządzać swoimi sklepami.',
    indexed: false,
  },
  {
    path: '/sign-up',
    title: 'Załóż konto',
    description: 'Załóż konto i otwórz sklep internetowy w dwie minuty.',
    indexed: false,
  },
  {
    path: '/reset-password',
    title: 'Nowe hasło',
    description: 'Ustaw nowe hasło do swojego konta.',
    indexed: false,
  },
];

/** Matches "/pricing" and "/pricing/". */
export function publicPage(pathname: string) {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  return PublicPages.find((page) => page.path === path);
}

/** The page's own on public pages, the site's name elsewhere. */
export function documentTitle(pathname: string) {
  const page = publicPage(pathname);
  if (!page) return Brand.name;
  return page.path === '/' ? page.title : `${page.title} | ${Brand.name}`;
}
