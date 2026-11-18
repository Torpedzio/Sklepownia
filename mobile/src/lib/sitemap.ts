import { PublicPages } from '@/constants/pages';

/** sitemap.xml: the public pages open to search engines, at `site` (an absolute address without a trailing slash). */
export function sitemapXml(site: string) {
  const urls = PublicPages.filter((page) => page.indexed)
    .map((page) => `  <url><loc>${escapeXml(site + page.path)}</loc></url>`)
    .join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

/**
 * robots.txt: everything may be crawled, so that search engines also see the noindex of the pages that carry it
 * (a page they may not fetch can still be listed, from links to it). Points to the sitemap.
 */
export function robotsTxt(site: string) {
  return `User-agent: *\nAllow: /\n\nSitemap: ${site}/sitemap.xml\n`;
}

function escapeXml(text: string) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
