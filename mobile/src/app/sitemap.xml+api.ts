import { siteUrl } from '@/lib/site';
import { sitemapXml } from '@/lib/sitemap';

export function GET() {
  return new Response(sitemapXml(siteUrl()), { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
}
