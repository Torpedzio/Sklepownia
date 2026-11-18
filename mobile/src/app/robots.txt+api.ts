import { siteUrl } from '@/lib/site';
import { robotsTxt } from '@/lib/sitemap';

export function GET() {
  return new Response(robotsTxt(siteUrl()), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
