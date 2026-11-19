import { PublicPages } from '@/constants/pages';

/** `site`: absolute, without a trailing slash. */
export function sitemapXml(site: string) {
  const urls = PublicPages.filter((page) => page.indexed)
    .map((page) => `  <url><loc>${escapeXml(site + page.path)}</loc></url>`)
    .join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

/** Allows everything, so crawlers also see the noindex of pages that carry it (an unfetched page can still be listed). */
export function robotsTxt(site: string) {
  return `User-agent: *\nAllow: /\n\nSitemap: ${site}/sitemap.xml\n`;
}

function escapeXml(text: string) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
