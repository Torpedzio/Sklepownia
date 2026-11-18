import { requestHeaders } from 'expo-server';
import { renderToStaticMarkup } from 'react-dom/server';

import Root from '@/app/+html';
import { documentTitle, HomeTitle, publicPage, PublicPages } from '@/constants/pages';
import { clearOf, Colors, colorVariablesCss, WebColors } from '@/constants/theme';
import { robotsTxt, sitemapXml } from '@/lib/sitemap';

jest.mock('expo-server', () => ({ origin: jest.fn(() => 'https://sklepownia.pl'), requestHeaders: jest.fn() }));

const DESKTOP = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const PHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1';

function visit(pathname: string, headers: Record<string, string> = { 'user-agent': DESKTOP }) {
  (requestHeaders as jest.Mock).mockReturnValue(new Headers(headers));
  return renderToStaticMarkup(
    <Root pathname={pathname}>
      <div id="root" />
    </Root>,
  );
}

const meta = (page: string, key: string) =>
  page.match(new RegExp(`<meta (?:name|property)="${key}" content="([^"]*)"`))?.[1];

afterEach(() => {
  delete process.env.SITE_URL;
});

test('a public page is described for search engines and link previews', () => {
  const page = visit('/pricing');

  expect(page).toContain('<html lang="pl"');
  expect(page).toContain('<title>Cennik | Sklepownia</title>');
  expect(meta(page, 'description')).toBe(publicPage('/pricing')!.description);
  expect(page).toContain('<link rel="canonical" href="https://sklepownia.pl/pricing"/>');
  expect(meta(page, 'og:url')).toBe('https://sklepownia.pl/pricing');
  expect(meta(page, 'og:title')).toBe('Cennik');
  expect(meta(page, 'og:image')).toBe('https://sklepownia.pl/og.png');
  expect(meta(page, 'twitter:card')).toBe('summary_large_image');
  expect(page).not.toContain('noindex');
});

test('the home page has its own title and says who runs the site', () => {
  const page = visit('/');

  expect(page).toContain(`<title>${HomeTitle}</title>`);
  expect(page).toContain('<link rel="canonical" href="https://sklepownia.pl/"/>');
  const data = JSON.parse(page.match(/<script type="application\/ld\+json">(.*?)<\/script>/)![1]);
  expect(data['@graph'].map((item: { '@type': string }) => item['@type'])).toEqual(['Organization', 'WebSite']);
});

test.each([
  ['the sign-in form', '/sign-in', 'Logowanie | Sklepownia'],
  ['the app behind sign-in', '/shops/12', 'Sklepownia'],
  ['an unknown address', '/nie-ma-takiej', 'Sklepownia'],
])('%s stays out of search results', (_, pathname, title) => {
  const page = visit(pathname);

  expect(page).toContain(`<title>${title}</title>`);
  expect(meta(page, 'robots')).toBe('noindex');
  expect(page).not.toContain('rel="canonical"');
  expect(page).not.toContain('og:');
});

test('SITE_URL sets the address where the server sees another one, e.g. behind a proxy', () => {
  process.env.SITE_URL = 'https://www.sklepownia.pl/';

  expect(visit('/about')).toContain('<link rel="canonical" href="https://www.sklepownia.pl/about"/>');
});

test.each([
  ['a phone', { 'user-agent': PHONE }, 'compact'],
  ['a computer', { 'user-agent': DESKTOP }, 'wide'],
  ['a browser saying it is on a phone', { 'user-agent': DESKTOP, 'sec-ch-ua-mobile': '?1' }, 'compact'],
  ['a browser saying it is not', { 'user-agent': PHONE, 'sec-ch-ua-mobile': '?0' }, 'wide'],
])('the page from the server is drawn for the window of %s', (_, headers, viewport) => {
  expect(visit('/', headers)).toContain(`data-viewport="${viewport}"`);
});

test('the page sets the colors of both modes before any script runs', () => {
  const page = visit('/');
  const css = colorVariablesCss();

  expect(page).toContain(css);
  for (const scheme of ['light', 'dark'] as const) {
    for (const value of Object.values(Colors[scheme])) expect(css).toContain(`:${value}`);
  }
  expect(css).toMatch(/@media \(prefers-color-scheme:dark\)\{:root\{--color-background:#0E1526;/);
  expect(WebColors.textSecondary).toBe('var(--color-text-secondary)');
});

test('fading into a color keeps its hue on phones and uses transparent in the browser', () => {
  expect(clearOf('#F4F6FA')).toBe('#F4F6FA00');
  expect(clearOf(WebColors.background)).toBe('transparent');
});

test('the browser tab names the page', () => {
  expect(documentTitle('/')).toBe(HomeTitle);
  expect(documentTitle('/contact/')).toBe('Kontakt | Sklepownia');
  expect(documentTitle('/billing')).toBe('Sklepownia');
});

test('the sitemap lists the pages open to search engines, and robots.txt points to it', () => {
  const xml = sitemapXml('https://sklepownia.pl');
  const listed = [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((match) => match[1]);

  expect(listed).toEqual(PublicPages.filter((page) => page.indexed).map((page) => `https://sklepownia.pl${page.path}`));
  expect(listed).toEqual([
    'https://sklepownia.pl/',
    'https://sklepownia.pl/about',
    'https://sklepownia.pl/pricing',
    'https://sklepownia.pl/contact',
  ]);
  expect(robotsTxt('https://sklepownia.pl')).toContain('Sitemap: https://sklepownia.pl/sitemap.xml');
});
