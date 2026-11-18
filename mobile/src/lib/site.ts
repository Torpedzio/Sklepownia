import { origin } from 'expo-server';

/**
 * The site's address for links that must be absolute (canonical, link previews, sitemap.xml), without
 * a trailing slash. `SITE_URL` sets it where the server can't see the visitor's address itself, e.g. behind
 * a proxy; otherwise it is the address of the request. Server only.
 */
export function siteUrl() {
  const configured = process.env.SITE_URL;
  if (configured) return configured.replace(/\/+$/, '');
  try {
    return (origin() ?? '').replace(/\/+$/, '');
  } catch {
    return '';
  }
}
